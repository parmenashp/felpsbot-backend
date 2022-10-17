from pydantic import BaseModel


class User(BaseModel):
    """Model for the user with object returned by Auth0 and the user discord id"""

    sub: str
    discord_id: str
    name: str
    nickname: str
    picture: str
    updated_at: str
