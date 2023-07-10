import os
import sys
import time

import humanize
from fastapi import Depends, FastAPI, Request
from loguru import logger

from core.prisma import prisma
from core.redis import redis
from core.twitch import twitch_api
from core.eventsub import eventsub
import routes.eventsub
import routes.gametime

from core.dependencies.auth import UserHasScope, get_current_auth0_user
from core.schemas.auth0 import User

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
    await prisma.connect()
    await twitch_api.authorize()
    await eventsub.connect_to_rabbitmq()


@app.on_event("shutdown")
async def shutdown():
    await redis.disconnect()
    await prisma.disconnect()


@app.get("/me", dependencies=[Depends(UserHasScope("profile"))])
async def get_me(me: User = Depends(get_current_auth0_user)) -> User:
    return me


app.include_router(routes.gametime.router)
app.include_router(routes.eventsub.router)
