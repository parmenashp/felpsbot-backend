from datetime import datetime
from typing import TypeVar

from app.core.database import database

_Self = TypeVar("_Self", bound="LastTimePlayed")


class LastTimePlayed:
    def __init__(self, streamer_id: str, game_id: str, last_played: datetime):
        self.streamer_id = streamer_id
        self.game_id = game_id
        self.last_played = last_played

    async def commit(self):
        async with database.db.acquire() as conn:
            async with conn.transaction():
                await conn.execute(
                    """
                    INSERT INTO last_time_played (streamer_id, game_id, last_played)
                    VALUES ($1, $2, $3)
                    ON CONFLICT (streamer_id, game_id) DO UPDATE SET last_played = $3
                    """,
                    int(self.streamer_id),
                    int(self.game_id),
                    self.last_played,
                )

    @classmethod
    async def update(cls, streamer_id: str, game_id: str):
        """Update the last time a game was played for a streamer to utc now"""
        await cls(streamer_id, game_id, datetime.utcnow()).commit()

    @classmethod
    async def from_database(cls: type[_Self], streamer_id: str, game_id: str) -> None | _Self:
        """Get a LastTimePlayed object from the database. Returns None if not found"""
        async with database.db.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT streamer_id, game_id, last_played
                FROM last_time_played
                WHERE streamer_id = $1 AND game_id = $2
                """,
                int(streamer_id),
                int(game_id),
            )
            if row:
                return cls(
                    streamer_id=str(row["streamer_id"]),
                    game_id=str(row["game_id"]),
                    last_played=row["last_played"],
                )
            return None
