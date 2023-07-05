from pydantic import BaseModel


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
