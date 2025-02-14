import os

from felpsbot_redis import Redis

from core.settings import settings

redis = Redis.from_url(settings.redis_url, decode_responses=True)
