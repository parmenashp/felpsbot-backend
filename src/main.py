import os
import sys
import time
from typing import Annotated

import humanize
from fastapi import Depends, FastAPI, Request, Security
from loguru import logger

import routes.eventsub
import routes.gametime
from core.dependencies.auth import get_current_auth0_user
from core.eventsub import eventsub
from core.prisma import prisma
from core.redis import redis
from core.schemas import auth0
from core.settings import settings
from core.twitch import twitch_api

humanize.i18n.activate("pt_BR")  # type: ignore   Set the locale for humanize to pt_BR

logger.remove()  # All cdefault handlers are removed
logger.add(sys.stderr, diagnose=False, level=os.getenv("LOG_LEVEL", "INFO"))

app = FastAPI(
    title="Felpsbot Backend API",
    description="API for the Felpsbot.",
    version="0.1.0",
    swagger_ui_init_oauth={
        "clientId": settings.auth0_client_id,
    },
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


@app.get("/me")
async def get_me(me: Annotated[auth0.User, Security(get_current_auth0_user, scopes=["profile"])]) -> auth0.User:
    return me


app.include_router(routes.gametime.router)
app.include_router(routes.eventsub.router)
