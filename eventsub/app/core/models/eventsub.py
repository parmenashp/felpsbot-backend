import os

import iso8601
from app.core.constants import CALLBACK_URL
from fastapi import HTTPException


class Transport:
    def __init__(self, data):
        self.method: str = data.get("method")
        self.callback: str = data.get("callback")
        self.secret: str | None = data.get("secret")

    def to_dict(self):
        return {
            "method": self.method,
            "callback": self.callback,
            "secret": self.secret,
        }


class SubscriptionRequest:
    """Model for a Twitch Eventsub Subscription creation request"""

    def __init__(self, type: str, condition: dict) -> None:
        self.type = type
        self.version = "1"
        self.condition = condition
        self.transport = Transport(
            {
                "method": "webhook",
                "callback": CALLBACK_URL,
                "secret": os.environ["EVENTSUB_SECRET_KEY"],
            }
        )

    @classmethod
    def stream_online(cls, broadcaster_user_id: str) -> "SubscriptionRequest":
        """Create a SubscriptionRequest for a stream.online event"""
        return cls("stream.online", {"broadcaster_user_id": broadcaster_user_id})

    @classmethod
    def stream_offline(cls, broadcaster_user_id: str) -> "SubscriptionRequest":
        """Create a SubscriptionRequest for a stream.offline event"""
        return cls("stream.offline", {"broadcaster_user_id": broadcaster_user_id})

    @classmethod
    def channel_update(cls, broadcaster_user_id: str) -> "SubscriptionRequest":
        """Create a SubscriptionRequest for a channel.update event"""
        return cls("channel.update", {"broadcaster_user_id": broadcaster_user_id})

    @classmethod
    def from_subscription(cls, subscription: "Subscription") -> "SubscriptionRequest":
        """Create a SubscriptionRequest from a Subscription"""
        return cls(subscription.type, subscription.condition)

    def to_dict(self) -> dict:
        return {
            "type": self.type,
            "version": self.version,
            "condition": self.condition,
            "transport": self.transport.to_dict(),
        }


class Subscription:
    def __init__(self, data):
        self.id: str = data.get("id")
        self.status: str = data.get("status")
        self.type: str = data.get("type")
        self.version: str = data.get("version")
        self.condition: dict = data.get("condition")
        self.created_at = iso8601.parse_date(data.get("created_at"))
        self.transport = Transport(data.get("transport"))
        self.cost: int = data.get("cost")

    def to_dict(self):
        return {
            "id": self.id,
            "status": self.status,
            "type": self.type,
            "version": self.version,
            "condition": self.condition,
            "created_at": self.created_at.isoformat(),
            "transport": self.transport.to_dict(),
            "cost": self.cost,
        }


class ChannelUpdateEvent:
    def __init__(self, data):
        self.broadcaster_user_id: str = data.get("broadcaster_user_id")
        self.broadcaster_user_login: str = data.get("broadcaster_user_login")
        self.broadcaster_user_name: str = data.get("broadcaster_user_name")
        self.title: str = data.get("title")
        self.language: str = data.get("language")
        self.category_id: str = data.get("category_id")
        self.category_name: str = data.get("category_name")
        self.is_mature: bool = data.get("is_mature")

    def to_dict(self):
        return {
            "broadcaster_user_id": self.broadcaster_user_id,
            "broadcaster_user_login": self.broadcaster_user_login,
            "broadcaster_user_name": self.broadcaster_user_name,
            "title": self.title,
            "language": self.language,
            "category_id": self.category_id,
            "category_name": self.category_name,
            "is_mature": self.is_mature,
        }


class StreamOfflineEvent:
    def __init__(self, data):
        self.broadcaster_user_id: str = data.get("broadcaster_user_id")
        self.broadcaster_user_login: str = data.get("broadcaster_user_login")
        self.broadcaster_user_name: str = data.get("broadcaster_user_name")

    def to_dict(self):
        return {
            "broadcaster_user_id": self.broadcaster_user_id,
            "broadcaster_user_login": self.broadcaster_user_login,
            "broadcaster_user_name": self.broadcaster_user_name,
        }


class StreamOnlineEvent:
    def __init__(self, data):
        self.id: str = data.get("id")
        self.broadcaster_user_id: str = data.get("broadcaster_user_id")
        self.broadcaster_user_login: str = data.get("broadcaster_user_login")
        self.broadcaster_user_name: str = data.get("broadcaster_user_name")
        self.type: str = data.get("type")
        self.started_at = iso8601.parse_date(data.get("started_at"))

    def to_dict(self):
        return {
            "id": self.id,
            "broadcaster_user_id": self.broadcaster_user_id,
            "broadcaster_user_login": self.broadcaster_user_login,
            "broadcaster_user_name": self.broadcaster_user_name,
            "type": self.type,
            "started_at": self.started_at,
        }


class Notification:
    def __init__(self, data: dict):
        self.subscription = Subscription(data=data["subscription"])
        type = self.subscription.type
        if type == "stream.online":
            self.event = StreamOnlineEvent(data=data["event"])
        elif type == "stream.offline":
            self.event = StreamOfflineEvent(data=data["event"])
        elif type == "channel.update":
            self.event = ChannelUpdateEvent(data=data["event"])
        else:
            raise HTTPException(400, "Unknown event type")

    def to_publish_dict(self):
        """Used to generate the notification to redis pubsub"""
        return {
            "type": self.subscription.type,
            "event": self.event.to_dict(),
        }
