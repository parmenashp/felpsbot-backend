import asyncio
import os
from datetime import datetime, timedelta
from functools import wraps
from urllib.parse import urljoin

import httpx
from loguru import logger

from core.constants import TWITCH_API_BASE_URL, TWITCH_OAUTH_URL
from core.redis import Redis, redis
from core.schemas.twitch import Channel, Stream

CACHE_CHANNEL_TTL = 60 * 5  # 5 minutes

cache_tasks = set()


# FIXME: NOT WORKING
def cache(name: str, return_type, params: list[str] | None = None, ttl: int = CACHE_CHANNEL_TTL):
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            if not callable(return_type):
                raise TypeError("Return type must have a callable constructor")
            key_params = [kwargs.get(param) for param in params if kwargs.get(param) is not None] if params else []
            if len(key_params) > 1:
                raise ValueError("Only one parameter can be used as a key")
            key = f"twitch:{name}:{key_params[0]}" if key_params else f"twitch:{name}"

            logger.debug(f"Checking cache for key {key}")
            cached = await redis.get_json(key)
            if cached:
                try:
                    return return_type(**cached)
                except TypeError:
                    logger.exception(f"Invalid cache data for key {key!r} with value {cached!r}")
                    raise

            logger.debug(f"{name} not found in cache. Fetching from API")
            result = await func(*args, **kwargs)
            if not isinstance(result, return_type) and result is not None:  # type: ignore
                raise TypeError(f"Return type of {func.__name__} must be {return_type}")

            if hasattr(result, "dict") and callable(result.dict):
                coro = redis.set_json(key, result.dict(), ttl=ttl)  # type: ignore
            else:
                coro = redis.set_json(key, result, ttl=ttl)  # type: ignore

            task = asyncio.create_task(coro)
            cache_tasks.add(task)
            task.add_done_callback(lambda t: cache_tasks.remove(t))

            return result

        return wrapper

    return decorator


class TwitchAPI:
    """A class for handling Twitch API requests"""

    def __init__(self, client_id: str, client_secret: str, redis: Redis) -> None:
        self._client_id = client_id
        self._client_secret = client_secret
        self._redis: Redis = redis
        self._httpx_client = httpx.AsyncClient()
        self._access_token: str | None = None
        self._access_token_expires: datetime | None = None

    async def shutdown(self):
        logger.info("Shutting down HTTPX Twitch client")
        await self._httpx_client.aclose()

    async def authorize(self):
        logger.info("Authorizing Twitch API")

        self._access_token: str | None = await self._redis.get("twitch:access_token")
        if self._access_token is None:
            logger.info("No cached access token found, generating new one")
            await self.generate_token()
            logger.info("Twitch API authorized")
            return

        ttl = await self._redis.get_ttl("twitch:access_token")
        if ttl:
            # -5 seconds just to be safe
            self._access_token_expires = datetime.now() + timedelta(seconds=ttl - 5)

        logger.info("Twitch API authorized")

    async def generate_token(self):
        logger.info("Generating new Twitch access token")
        try:
            params = {
                "client_id": self._client_id,
                "client_secret": self._client_secret,
                "grant_type": "client_credentials",
            }
            r = await self._httpx_client.post(TWITCH_OAUTH_URL, params=params)
            response: dict = r.json()
        except httpx.RequestError as e:
            logger.exception("Twitch access token request failed")
            raise e

        if "access_token" in response:
            self._access_token = str(response["access_token"])
            self._access_token_expires = datetime.utcnow() + timedelta(seconds=response["expires_in"])
            await self._redis.set("twitch:access_token", self._access_token, ttl=response["expires_in"])
            logger.info(f"New Twitch access token generated")
        elif "message" in response:
            logger.error(f"Twitch access token request failed. {response}")
            logger.debug(
                f"Access token request to {TWITCH_OAUTH_URL} failed. "
                f"Status code: {r.status_code}, Headers: {r.headers}, Body: {response}"
            )
        else:
            logger.error(f"Twitch access token request failed. {response}")
            logger.debug(
                f"Access token request to {TWITCH_OAUTH_URL} failed. "
                f"Status code: {r.status_code}, Headers: {r.headers}, Body: {response}"
            )

    async def _ensure_token(self):
        logger.debug("Ensuring Twitch access token is set and not expired")
        if (not self._access_token) or (self._access_token_expires is None):
            logger.debug("Twitch access token is set")
            return await self.generate_token()

        elif self._access_token_expires is not None:
            if datetime.utcnow() > self._access_token_expires:
                logger.debug("Twitch access token expired")
                return await self.generate_token()
        logger.debug("Twitch access token is set and not expired")

    async def get(self, path, params=None) -> httpx.Response:
        """Makes an authenticated GET request to the Twitch API"""
        url = urljoin(TWITCH_API_BASE_URL, path)
        await self._ensure_token()
        headers = {
            "Client-ID": self._client_id,
            "Authorization": f"Bearer {self._access_token}",
        }

        # FUTURE: handle rate limit
        try:
            logger.debug(
                f"Making GET request to {url} with params {params}\n" f"Headers: {headers}",
            )
            response = await self._httpx_client.get(url, params=params, headers=headers)
            logger.debug(
                f"Get request to {url} with params {params} took {response.elapsed}.\n"
                f"Headers: {response.headers}\n"
                f"Body: {response.json()}"
            )
        except httpx.RequestError as e:
            logger.exception(f"Request to {url} with params {params} failed")
            raise e

        response.raise_for_status()
        return response

    async def post(self, path: str, json: dict | str | None = None, params: dict | None = None) -> httpx.Response:
        """Makes an authenticated POST request to the Twitch API"""
        url = urljoin(TWITCH_API_BASE_URL, path)
        await self._ensure_token()
        headers = {
            "Client-ID": self._client_id,
            "Authorization": f"Bearer {self._access_token}",
        }
        if json:
            headers["Content-Type"] = "application/json"

        # FUTURE: handle rate limit
        try:
            logger.debug(
                f"Making Post request to {url} with params {params}\n" f"Headers: {headers}\n" f"Body: {json}\n",
            )
            response = await self._httpx_client.post(
                url,
                json=json,
                params=params,
                headers=headers,
            )
            logger.debug(
                f"Post request to {url} with params {params} took {response.elapsed}.\n"
                f"Headers: {response.headers}\n"
                f"Body: {response.json()}"
            )
        except httpx.RequestError as e:
            logger.exception(f"Request to {url} with params {params} and body {json} failed")
            raise e

        response.raise_for_status()
        return response

    async def delete(self, path: str, params: dict | None = None) -> httpx.Response:
        """Makes an authenticated DELETE request to the Twitch API"""
        url = urljoin(TWITCH_API_BASE_URL, path)
        await self._ensure_token()
        headers = {"Client-ID": self._client_id, "Authorization": f"Bearer {self._access_token}"}

        # FUTURE: handle rate limit
        try:
            logger.debug(
                f"Making GET request to {url} with params {params}" f"Headers: {headers}",
            )
            response = await self._httpx_client.delete(url, params=params, headers=headers)
            logger.debug(
                f"Delete request to {url} with params {params} took {response.elapsed}.\n"
                f"Headers: {response.headers}\n"
                f"Body: {response.json()}"
            )
        except httpx.RequestError as e:
            logger.exception(f"Request to {url} with params {params} failed")
            raise e

        response.raise_for_status()
        return response

    async def get_channel(self, broadcaster_id: int) -> Channel | None:
        """Fetches channel information for a user."""

        logger.debug(f"Fetching channel {broadcaster_id} from API")
        response = await self.get("channels", params={"broadcaster_id": broadcaster_id})
        if channels := [Channel(**x) for x in response.json()["data"]]:
            return channels[0]
        return None

    async def get_stream(self, user_id: int) -> Stream | None:
        """Fetches stream information of a user."""

        logger.debug(f"Fetching stream of user {user_id} from API")
        response = await self.get("streams", params={"user_id": user_id})
        if streams := [Stream(**x) for x in response.json()["data"]]:
            return streams[0]
        return None


twitch_api = TwitchAPI(os.environ["TWITCH_CLIENT_ID"], os.environ["TWITCH_CLIENT_SECRET"], redis)
