import os
from typing import Optional

import orjson
from loguru import logger
from redis import asyncio as aioredis


class RedisConnectionError(Exception):
    pass


class Redis:
    def __init__(self, url: str) -> None:
        self._url = url
        self._redis = aioredis.from_url(self._url, decode_responses=True, encoding="utf-8")
        self.ready = False

    async def connect(self) -> bool:
        """Connects with Redis, raises `RedisConnectionError`if not able to connect."""
        logger.info(f"Connecting to Redis")
        try:
            if await self._redis.ping():
                logger.info("Connected to Redis")
                self.ready = True
                return True
            raise RedisConnectionError("Could not connect to Redis, ping not ponged")

        except aioredis.ConnectionError:
            raise RedisConnectionError("Could not connect to Redis")

    async def disconnect(self) -> None:
        """Disconnects from Redis."""
        logger.info("Disconnecting from Redis")
        await self._redis.close()

    async def get(self, key) -> Optional[str]:
        """Get the value at `key`."""
        if self._redis:
            v = await self._redis.get(key)
            if v:
                logger.debug(f"Cache hit: {key}")
                return v
            logger.debug(f"Cache miss: {key}")

    async def set(self, key: str, value: str, ttl=300):
        """Set the value at `key` to `value`."""
        if self._redis:
            r = await self._redis.set(key, value, ex=ttl)
            if r:
                logger.debug(f"Cache set: {key}")
                return r

    async def delete(self, key) -> Optional[bool]:
        """Delete the value at `key`."""
        if self._redis:
            r = await self._redis.delete(key)
            if r:
                logger.debug(f"Key deleted: {key}")
                return True

    async def get_ttl(self, key: str) -> Optional[int]:
        """Get the time to live for `key`."""
        if self._redis:
            return await self._redis.ttl(key)

    async def get_json(self, key: str) -> Optional[dict]:
        """Get a JSON value at `key`."""
        if self._redis:
            v = await self.get(key)
            if v:
                try:
                    return orjson.loads(v)
                except orjson.JSONDecodeError:
                    logger.error(f"Could not decode JSON for key {key}")

    async def set_json(self, key: str, value: dict | list, ttl=300):
        """Set a JSON value at `key`` to `value`."""
        if self._redis:
            try:
                v = orjson.dumps(value).decode("utf-8")
                return await self.set(key, v, ttl=ttl)
            except orjson.JSONEncodeError:
                logger.error(f"Could not encode JSON for key {key}")

    async def publish(self, channel: str, data: dict) -> int:
        """Publish `message` on `channel`.
        Returns the number of subscribers the message was delivered to"""
        if not self._redis:
            logger.warning(f"Message on {channel} not published due to missing Redis connection")
            return 0
        try:
            v = orjson.dumps(data)
            num = await self._redis.publish(channel, v)
            logger.info(f"Published message on channel {channel} to {num} subscribers")
            return num
        except orjson.JSONEncodeError:
            logger.error(f"Could not encode JSON for publishing on channel {channel}")
            return 0

    async def mget(self, keys: list[str], json: bool = False, ignore_missing: bool = True) -> tuple[list, list[str]]:
        """Returns the values of all specified keys.
        For every key that does not hold a string value or does not exist, None is returned.

        If `json` is True, return a list of decoded JSON values.

        If `ignore_missing` is True, only return values that are not None.
        """
        redis_list = await self._redis.mget(keys)
        missing_keys = []

        if None in redis_list:
            for i, v in enumerate(redis_list):
                if v is None:
                    missing_keys.append(keys[i])

        if not json:
            return redis_list, missing_keys

        if ignore_missing:
            return [orjson.loads(v) for v in redis_list if v is not None], missing_keys
        else:
            return [orjson.loads(v) if v is not None else None for v in redis_list], missing_keys


redis = Redis(os.getenv("REDIS_URL", "redis://localhost:6379"))
