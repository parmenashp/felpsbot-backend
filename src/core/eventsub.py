import os
from collections import deque
from datetime import datetime
from json import JSONDecodeError
from typing import TYPE_CHECKING

import aio_pika
import orjson
from aio_pika.abc import AbstractChannel
from fastapi import HTTPException, Request, status
from fastapi.responses import PlainTextResponse
from loguru import logger

from core.models.eventsub import Notification, Subscription, SubscriptionRequest
from core.prisma import prisma
from core.settings import settings
from core.twitch import TwitchAPI, twitch_api

if TYPE_CHECKING:
    from core.twitch import TwitchAPI

from aio_pika.abc import AbstractChannel, AbstractExchange

MAX_LEN_DEQUE = 15

ACKNOWLEDGE_RESPONSE = PlainTextResponse("Acknowledged", status_code=status.HTTP_200_OK)


class EventSub:
    def __init__(self, twitch_api: TwitchAPI) -> None:
        self.twitch_api = twitch_api
        self._processed = deque(maxlen=MAX_LEN_DEQUE)
        self.subscriptions = []
        self.rabbit_channel: AbstractChannel
        self.rabbit_exchange: AbstractExchange
        self._rabbitmq_exchange_name = settings.rabbitmq_exchange_name
        self._rabbitmq_queue_name = settings.rabbitmq_queue_name
        self._twitch_api_base_url = settings.twitch_api_base_url
        self._rabbitmq_url = settings.rabbitmq_url

    async def connect_to_rabbitmq(self):
        logger.info("Connecting to rabbitmq")
        connection = await aio_pika.connect_robust(self._rabbitmq_url)
        self.rabbit_channel = await connection.channel()
        self.rabbit_exchange = await self.rabbit_channel.declare_exchange(
            self._rabbitmq_exchange_name, aio_pika.ExchangeType.FANOUT, durable=True
        )

    async def callback_handler(self, request: Request):
        try:
            d_body = await request.json()
        except JSONDecodeError:
            d_body = await request.body()
        logger.debug(f"Received a eventsub callback with body: {d_body}." f"\nHeaders: {request.headers}")

        try:
            msg_type = request.headers["Twitch-Eventsub-Message-Type"]
        except KeyError:
            logger.info("Invalid eventsub request, missing message type header")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Missing message type header.",
            )

        logger.info(f"Received an eventsub webhook message of type {msg_type}")

        if msg_type == "notification":
            body: dict = await request.json()
            return await self._handle_notification(Notification(data=body), request)

        elif msg_type == "webhook_callback_verification":
            return await self._handle_verification(request)

        elif msg_type == "revocation":
            body: dict = await request.json()
            return await self._handle_revocation(Subscription(data=body))

        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid message type.",
            )

    async def _handle_notification(self, notification: Notification, request: Request):
        logger.info(
            f"Received a {notification.subscription.type} "
            f"notification for {notification.event.broadcaster_user_name}"
        )

        # self._processed keeps track of the last X notifications ID, as Twitch
        # can send more than one notification for the same event
        if request.headers.get("Twitch-Eventsub-Message-Id") in self._processed:
            logger.info(f"Notification already processed. Skipping")
            return ACKNOWLEDGE_RESPONSE

        self._processed.append(request.headers.get("Twitch-Eventsub-Message-Id"))

        # TODO: Publish to rabbit and update the database in a background task after the response is sent

        if notification.subscription.type == "channel.update":
            await self._update_last_time_played(notification)

        logger.info(f"Publishing notification to rabbitmq")
        body = orjson.dumps(notification.to_publish_dict())
        await self.rabbit_exchange.publish(
            aio_pika.Message(body=body, delivery_mode=aio_pika.DeliveryMode.PERSISTENT),
            routing_key="",  # RabbitMQ ignores the routing key for fanout exchanges, but it is required
        )

        return ACKNOWLEDGE_RESPONSE

    async def _handle_verification(self, request: Request):
        body: dict = await request.json()
        logger.info(f"Responding to challenge")
        return PlainTextResponse(content=body.get("challenge"))

    async def _handle_revocation(self, subscription: Subscription):
        logger.warning(
            "Received a revocation message from Twitch. "
            f"Type: {subscription.type}, condition: {subscription.condition}"
        )
        logger.info("Trying to resubscribe to this event")
        await self.subscribe(SubscriptionRequest.from_subscription(subscription), check_if_exists=False)
        return ACKNOWLEDGE_RESPONSE

    async def _update_last_time_played(self, notification: Notification):
        if not notification.event.category_id:  # type: ignore
            logger.info("Game is not set, skipping last time played update")
            return

        logger.info(
            f"Updating last time played {notification.event.category_name} "  # type: ignore
            f"for streamer {notification.event.broadcaster_user_name}"
        )
        streamer_id: str = notification.event.broadcaster_user_id
        game_id: str = notification.event.category_id  # type: ignore

        await self.upsert_game(game_id, notification.event.category_name)  # type: ignore
        await self.upsert_last_time_played(streamer_id, game_id)

    async def upsert_game(self, game_id: str | int, game_name: str):
        logger.info(f"Upserting game {game_name} ({game_id})")
        await prisma.game.upsert(
            where={"twitch_id": int(game_id)},
            data={
                "create": {"twitch_id": int(game_id), "name": game_name, "image_url": ""},
                "update": {"name": game_name},
            },
        )

    async def upsert_last_time_played(self, streamer_id: str | int, game_id: str | int):
        logger.info(f"Upserting last time played for streamer {streamer_id} and game {game_id}")
        await prisma.lasttimeplayed.upsert(
            where={"game_streamer_unique": {"game_id": int(game_id), "streamer_id": int(streamer_id)}},
            data={
                "create": {"game_id": int(game_id), "streamer_id": int(streamer_id)},
                "update": {"last_time": datetime.utcnow()},
            },
        )

    async def fetch_subscriptions(self):
        logger.info("Fetching eventsub subscriptions")

        response = await self.twitch_api.get(self._twitch_api_base_url + "eventsub/subscriptions")
        self.subscriptions = [Subscription(data=sub) for sub in response.json()["data"]]
        logger.info(f"Fetched {len(self.subscriptions)} subscriptions")

    async def subscribe(self, sub_request: SubscriptionRequest, check_if_exists: bool = True) -> bool | dict:
        """Subscribe to a Twitch eventsub event. If check_if_exists is True, it will check if
        another subscription already exists for the same event, condition and transport method."""

        logger.info(f"Subscribing to {sub_request.type} with condition {sub_request.condition}")

        # TODO: check the number of subscriptions, as there is a
        # limit of 3 subscriptions for the same type and condition
        if check_if_exists:
            await self.fetch_subscriptions()
            for sub in self.subscriptions:
                if (
                    sub.type == sub_request.type
                    and sub.condition == sub_request.condition
                    and sub.status == "enabled"
                    and sub.transport.callback == sub_request.transport.callback
                ):
                    logger.info(f"Subscription with condition {sub_request.condition} already exists, skipping...")
                    return False

        response = await self.twitch_api.post(
            self._twitch_api_base_url + "eventsub/subscriptions", json=sub_request.to_dict()
        )

        # TODO: remover os esses debugs e colocar eles no post get delete do twitch_api

        logger.debug(f"Eventsub requested with body: {response.request.content}")
        logger.debug(f"Twitch response for the eventsub request: {response.json()}" f"\nHeaders: {response.headers}")
        if response.status_code == status.HTTP_202_ACCEPTED:
            logger.info(f"Subscription to {sub_request.type} with condition {sub_request.condition} accepted")
            return response.json()

        return False

    async def unsubscribe(self, subscription: Subscription) -> bool:
        """Unsubscribe from a Twitch eventsub event."""

        logger.info(f"Unsubscribing from {subscription.type} with condition {subscription.condition}")

        response = await self.twitch_api.delete(
            self._twitch_api_base_url + f"eventsub/subscriptions?id={subscription.id}"
        )
        if response.status_code == status.HTTP_204_NO_CONTENT:
            logger.info(f"Unsubscription from {subscription.type} with condition {subscription.condition} accepted")
            return True

        return False


eventsub = EventSub(twitch_api)
