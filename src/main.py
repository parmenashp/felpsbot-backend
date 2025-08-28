import os
import sys
import time
from typing import Annotated

import humanize
from fastapi import Depends, FastAPI, Request, Security
from fastapi.middleware.cors import CORSMiddleware
from loguru import logger

import routes.eventsub
from routes.v1 import gametime as gametime_v1
from routes.v2 import gametime as gametime_v2
from routes.v1 import games as games_v1
from routes.v1 import subscriptions as subscriptions_v1
from core.dependencies.auth import get_current_auth0_user
from core.eventsub import eventsub
from core.prisma import prisma
from core.redis import redis
from core.schemas import auth0
from core.twitch import twitch_api

humanize.i18n.activate("pt_BR")  # type: ignore   Set the locale for humanize to pt_BR

logger.remove()  # All cdefault handlers are removed
logger.add(sys.stderr, diagnose=False, level=os.getenv("LOG_LEVEL", "INFO"))

app = FastAPI(
    title="Felpsbot Backend API",
    description="API for the Felpsbot.",
    version="0.1.0",
    swagger_ui_init_oauth={
        "clientId": os.getenv("AUTH0_CLIENT_ID"),
    },
)


# CORS configuration
_default_cors = "http://localhost:5173, http://127.0.0.1:5173, https://felpsbot.mitsuaky.dog"
_origins = [origin.strip() for origin in os.getenv("CORS_ORIGINS", _default_cors).split(",") if origin.strip()]

app.add_middleware(
    CORSMiddleware,
    allow_origins=_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
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


app.include_router(routes.eventsub.router)
app.include_router(gametime_v1.router, prefix="/v1")
app.include_router(gametime_v2.router, prefix="/v2")
app.include_router(games_v1.router, prefix="/v1")
app.include_router(subscriptions_v1.router, prefix="/v1")
