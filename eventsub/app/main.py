import os
import sys
import time

import humanize
from fastapi import FastAPI, Request
from loguru import logger

from app.core.database import database
from app.core.redis import redis
from app.core.twitch import twitch_api
from app.routes import eventsub

humanize.i18n.activate("pt_BR")  # type: ignore   Set the locale for humanize to pt_BR

logger.remove()  # All cdefault handlers are removed
logger.add(sys.stderr, diagnose=False, level=os.getenv("LOG_LEVEL", "INFO"))

app = FastAPI(
    title="TwitchIntegration",
    description="FelpsBot service to comunicate with Twitch Eventsub",
    version="0.1.0",
)


@app.middleware("http")
async def add_process_time_header(request: Request, call_next):
    """Used to add a header to the response to show how long the request took."""
    start_time = time.time()
    response = await call_next(request)
    response.headers["X-Process-Time"] = f"{(time.time() - start_time) * 1000:.2f} ms"
    return response


@app.on_event("startup")
async def startup():
    await redis.connect()
    await database.connect()
    await twitch_api.authorize()


app.include_router(eventsub.router)
