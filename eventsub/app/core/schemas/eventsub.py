from datetime import datetime

from pydantic import BaseModel


class Transport(BaseModel):
    """Model for a Twitch Eventsub Transport"""

    method: str
    callback: str


class Subscription(BaseModel):
    """Model for a Twitch Eventsub Subscription"""

    id: str
    status: str
    type: str
    version: str
    condition: dict
    created_at: datetime
    transport: Transport
    cost: int


class SubscriptionCreate(BaseModel):
    """Model for a Twitch Eventsub Subscription creation request of types:
    `stream.online`, `stream.offline`, `channel.update`"""

    type: str
    broadcaster_user_id: str


class Game(BaseModel):
    """Model for a Twitch Game"""

    id: str
    name: str
    box_art_url: str


class Stream(BaseModel):
    """Model for a Twitch Stream"""

    broadcaster_id: str
    broadcaster_login: str
    broadcaster_name: str
    broadcaster_language: str
    game_id: str
    game_name: str
    title: str
    delay: int
