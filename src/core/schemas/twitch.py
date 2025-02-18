from pydantic import BaseModel


class Stream(BaseModel):
    """Model for a Twitch Stream"""

    id: str
    user_id: str
    user_login: str
    user_name: str
    game_id: str
    game_name: str
    type: str
    title: str
    tags: list[str]
    viewer_count: int
    started_at: str
    language: str
    thumbnail_url: str
    tag_ids: list[str]
    is_mature: bool


class Channel(BaseModel):
    """Model for a Twitch Channel"""

    broadcaster_id: str
    broadcaster_login: str
    broadcaster_name: str
    game_name: str
    game_id: str
    broadcaster_language: str
    title: str
    delay: int


class Game(BaseModel):
    """Model for a Twitch Game"""

    id: str
    name: str
    box_art_url: str
