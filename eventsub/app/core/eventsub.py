from collections import deque
from json import JSONDecodeError
from typing import TYPE_CHECKING

from app.core.models.database import LastTimePlayed
from app.core.models.eventsub import Notification, Subscription, SubscriptionRequest
from app.core.redis import Redis, redis
from app.core.twitch import TWITCH_API_BASE_URL, TwitchAPI, twitch_api
from fastapi import HTTPException, Request, status
from fastapi.responses import PlainTextResponse
from loguru import logger

if TYPE_CHECKING:
    from app.core.twitch import TwitchAPI

MAX_LEN_DEQUE = 10

PUB_SUB_CHANNEL = "twitch:eventsub"

ACKNOWLEDGE_RESPONSE = PlainTextResponse("Acknowledged", status_code=status.HTTP_200_OK)


class EventSub:
    def __init__(self, twitch_api: TwitchAPI, redis: Redis) -> None:
        self.twitch_api = twitch_api
        self.redis = redis
        self._processed = deque(maxlen=MAX_LEN_DEQUE)
        self.subscriptions = []

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
            logger.debug(f"Notification already processed. Skipping")
            return ACKNOWLEDGE_RESPONSE

        self._processed.append(request.headers.get("Twitch-Eventsub-Message-Id"))

        # TODO: Publish to redis and update the database in a background task after the response is sent

        # Update the last time the game was played for the streamer
        if notification.subscription.type == "channel.update":
            await self._update_last_time_played(notification)
        # Publish the notification to the redis pubsub channel
        await redis.publish(PUB_SUB_CHANNEL, notification.to_publish_dict())

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
            logger.info("Game is not set, skipping")
            return

        logger.info(
            f"Updating last time played {notification.event.category_name} "  # type: ignore
            f"for streamer {notification.event.broadcaster_user_name}"
        )
        streamer_id: str = notification.event.broadcaster_user_id
        game_id: str = notification.event.category_id  # type: ignore
        await LastTimePlayed.update(streamer_id=streamer_id, game_id=game_id)

    async def fetch_subscriptions(self):
        logger.info("Fetching eventsub subscriptions")

        response = await self.twitch_api.get(TWITCH_API_BASE_URL + "eventsub/subscriptions")
        self.subscriptions = [Subscription(data=sub) for sub in response.json()["data"]]
        logger.debug(f"Fetched {len(self.subscriptions)} subscriptions")

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
            TWITCH_API_BASE_URL + "eventsub/subscriptions", json=sub_request.to_dict()
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

        response = await self.twitch_api.delete(TWITCH_API_BASE_URL + f"eventsub/subscriptions?id={subscription.id}")
        if response.status_code == status.HTTP_204_NO_CONTENT:
            logger.info(f"Unsubscription from {subscription.type} with condition {subscription.condition} accepted")
            return True

        return False


eventsub = EventSub(twitch_api, redis)
