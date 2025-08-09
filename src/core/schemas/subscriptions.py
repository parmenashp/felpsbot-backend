from datetime import datetime
from typing import Optional

from pydantic import BaseModel, root_validator


class SubscriptionItem(BaseModel):
    gameId: int
    name: Optional[str]
    imageUrl: Optional[str]
    createdAt: Optional[str]


class CreateSubscriptionRequest(BaseModel):
    gameId: Optional[int] = None
    gameName: Optional[str] = None

    @root_validator
    def exactly_one_field(cls, values):
        game_id = values.get("gameId")
        game_name = values.get("gameName")
        if bool(game_id) == bool(game_name):
            raise ValueError("Provide exactly one of gameId or gameName")
        return values


class SubscriptionCreated(BaseModel):
    gameId: int
    name: str
    imageUrl: str


