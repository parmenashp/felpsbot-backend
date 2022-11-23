from datetime import datetime, timezone
from typing import TypeVar

from app.core.database import Database

_Self = TypeVar("_Self", bound="LastTimePlayed")


class LastTimePlayed:
    def __init__(
        self, database: Database, streamer_id: str, game_id: str, last_played: datetime = datetime.now(tz=timezone.utc)
    ):
        self._database = database
        self.streamer_id = streamer_id
        self.game_id = game_id
        self.last_played = last_played

    async def commit(self):
        async with self._database.db.acquire() as conn:
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

    async def delete(self):
        async with self._database.db.acquire() as conn:
            r = await conn.execute(
                """
                DELETE FROM last_time_played
                WHERE streamer_id = $1 AND game_id = $2
                """,
                int(self.streamer_id),
                int(self.game_id),
            )
            if r == "DELETE 0":
                raise ValueError("No rows deleted")

    async def update(self, streamer_id: str, game_id: str):
        """Update the last time a game was played for a streamer to utc now"""
        self.streamer_id = streamer_id
        self.game_id = game_id
        await self.commit()

    @classmethod
    async def from_database(cls: type[_Self], database: Database, streamer_id: str, game_id: str) -> None | _Self:
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
                    database,
                    streamer_id=str(row["streamer_id"]),
                    game_id=str(row["game_id"]),
                    last_played=row["last_played"],
                )
            return None
