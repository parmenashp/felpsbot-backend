import os
from typing import AsyncGenerator

import asyncpg
from loguru import logger


class DatabaseNotConnected(Exception):
    pass


class Database:
    def __init__(self):
        self._db = None
        self._url = os.environ["DATABASE_URL"]

    async def connect(self):
        """Connect to the database."""
        logger.info(f"Connecting to database at {self._url}")
        try:
            self._db = await asyncpg.create_pool(self._url)
            logger.info("Connected to database")
            self.ready = True
            return True

        except asyncpg.exceptions.PostgresConnectionError as e:
            logger.error("Could not connect to database")
            raise e

    @property
    def db(self) -> asyncpg.Pool:
        """Acquire a connection from the database pool."""
        if not self._db:
            raise DatabaseNotConnected("Database not connected")

        return self._db


database = Database()
