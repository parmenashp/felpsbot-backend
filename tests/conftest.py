import logging
from typing import AsyncGenerator
from unittest import mock

import freezegun
import pytest
import pytest_asyncio
from _pytest.logging import caplog as _caplog
from asgi_lifespan import LifespanManager
from httpx import AsyncClient
from loguru import logger
from utils import get_or_create_event_loop

import prisma
from core.schemas.twitch import Channel, Game
from main import app
from prisma import Prisma

# (workaround) mock the _close_event_loop from pytest-asyncio
# to avoid closing the event loop after the tests, since we are
# using the same event loop for the tests and the app.
mock.patch("pytest_asyncio.plugin._close_event_loop", lambda: None).start()

freezegun.configure(extend_ignore_list=["loguru", "uvicorn", "httpx, prisma, fastapi"])  # type: ignore


FELPS_CHANNEL = Channel(
    broadcaster_id="30672329",
    broadcaster_login="felps",
    broadcaster_name="Felps",
    game_id="509658",
    broadcaster_language="pt-br",
    game_name="Just Chatting",
    delay=0,
    title="",
)

JUST_CHATTING_GAME = Game(
    id="509658",
    name="Just Chatting",
    box_art_url="https://static-cdn.jtvnw.net/ttv-boxart/Just%20Chatting-{width}x{height}.jpg",
)


@pytest.fixture
def caplog(_caplog):
    class PropogateHandler(logging.Handler):
        def emit(self, record):
            logging.getLogger(record.name).handle(record)

    logger.add(PropogateHandler(), format="{message}")
    yield _caplog


@pytest.mark.filterwarnings("ignore::DeprecationWarning")
@pytest.fixture(scope="session")
def event_loop():
    loop = get_or_create_event_loop()
    return loop


@pytest_asyncio.fixture(scope="session")
async def prisma_client():
    prisma_client = prisma.get_client()
    await setup_db(prisma_client)
    yield prisma_client
    await teardown_db(prisma_client)


@pytest_asyncio.fixture(scope="session")
async def test_client() -> AsyncGenerator[AsyncClient, None]:
    async with AsyncClient(app=app, base_url="http://test") as ac, LifespanManager(app):
        yield ac


async def setup_db(client: Prisma) -> None:
    await client.streamer.upsert(
        where={"twitch_id": int(FELPS_CHANNEL.broadcaster_id)},
        data={
            "create": {
                "twitch_id": int(FELPS_CHANNEL.broadcaster_id),
                "name": FELPS_CHANNEL.broadcaster_name,
            },
            "update": {},
        },
    )
    await client.game.upsert(
        where={"twitch_id": int(JUST_CHATTING_GAME.id)},
        data={
            "create": {
                "twitch_id": int(JUST_CHATTING_GAME.id),
                "name": JUST_CHATTING_GAME.name,
                "image_url": JUST_CHATTING_GAME.box_art_url,
            },
            "update": {},
        },
    )
    await client.lasttimeplayed.delete_many({})


async def teardown_db(client: Prisma) -> None:
    pass
