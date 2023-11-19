from datetime import datetime, timezone
from unittest import mock

import freezegun
import pytest
import pytest_asyncio
from conftest import FELPS_CHANNEL
from httpx import AsyncClient

from core.dependencies.twitch import twitch_api
from prisma import Prisma

pytestmark = pytest.mark.asyncio


@pytest_asyncio.fixture(scope="class")
async def setup_lasttimeplayed(prisma_client: Prisma):
    await prisma_client.lasttimeplayed.create(
        data={
            "game_id": 509658,
            "streamer_id": 30672329,
            "last_time": datetime(2021, 1, 1, 0, 0, 0, tzinfo=timezone.utc),
        }
    )
    try:
        yield
    finally:
        await prisma_client.lasttimeplayed.delete(
            where={"game_streamer_unique": {"game_id": 509658, "streamer_id": 30672329}}
        )


class TestStreamGameTime:
    # class just as workaround to the fixture scope problem, cause
    # I want to only run the teardown after all the parametrized tests are done

    @pytest.mark.parametrize(
        "time_to_freeze, expected_text",
        [
            ("2021-01-01 00:00:00", "0 segundo"),
            ("2021-01-01 00:01:02", "1 minuto e 2 segundos"),
            ("2021-01-01 01:02:03", "1 hora, 2 minutos e 3 segundos"),
            ("2022-03-06 04:05:06", "1 ano, 2 meses, 3 dias, 4 horas, 5 minutos e 6 segundos"),
        ],
    )
    async def test_streamgametime(
        self,
        time_to_freeze: str,
        expected_text: str,
        test_client: AsyncClient,
        setup_lasttimeplayed,
    ):
        with mock.patch.object(twitch_api, "get_channel", return_value=FELPS_CHANNEL):
            with freezegun.freeze_time(time_to_freeze, tz_offset=0):
                response = await test_client.get("/streamgametime/30672329")
                assert response.status_code == 200
                print(response.text)
                print(expected_text)
                assert response.text == expected_text


async def test_streamgametime_no_channel(test_client: AsyncClient):
    with mock.patch.object(twitch_api, "get_channel", return_value=None):
        response = await test_client.get("/streamgametime/2147483647")
        assert response.status_code == 404


async def test_streamgametime_no_last_time_found(test_client):
    with mock.patch.object(twitch_api, "get_channel", return_value=FELPS_CHANNEL):
        response = await test_client.get("/streamgametime/30672329")
        assert response.status_code == 200
        assert response.text == "desconhecido"


async def test_streamgametime_invalid_streamer_id(
    test_client: AsyncClient,
):
    with mock.patch.object(twitch_api, "get_channel", return_value=None):
        response = await test_client.get("/streamgametime/invalid_streamer_id")
        assert response.status_code == 422
        response = await test_client.get("/streamgametime/9898989898989898989")
        assert response.status_code == 422
        response = await test_client.get("/streamgametime/0")
        assert response.status_code == 422
