import asyncio
import logging
import os
from datetime import datetime, timedelta
from unittest import mock

import freezegun
import httpx
import pytest
import pytest_asyncio

from core.twitch import Channel, TwitchAPI, cache, cache_tasks, redis

FAKE_ACCESS_TOKEN = "test_access_token"
EXPIRES_IN = 3600

pytestmark = pytest.mark.asyncio


@pytest_asyncio.fixture
async def twitch():
    if not redis.ready:
        await redis.connect()
    twitch_api = TwitchAPI(os.environ["TWITCH_CLIENT_ID"], os.environ["TWITCH_CLIENT_SECRET"], redis)
    yield twitch_api


@pytest_asyncio.fixture
async def twitch_authorized(twitch: TwitchAPI):
    await twitch.authorize()
    yield twitch


@pytest.mark.asyncio
async def test_get_channel(twitch_authorized):
    result = await twitch_authorized.get_channel(30672329)
    assert isinstance(result, Channel)
    assert result.broadcaster_id == "30672329"
    assert result.broadcaster_login == "felps"


@pytest.fixture
def mocked_token_post():
    response = {"access_token": FAKE_ACCESS_TOKEN, "expires_in": EXPIRES_IN}
    with mock.patch.object(httpx.AsyncClient, "post", return_value=httpx.Response(200, json=response)) as mock_post:
        yield mock_post


@pytest_asyncio.fixture(scope="function")
async def teardown_redis():
    yield
    await redis._redis.flushdb()


@freezegun.freeze_time()
async def test_generate_token(twitch: TwitchAPI, mocked_token_post):
    assert twitch._access_token is None
    assert twitch._access_token_expires is None

    await twitch.generate_token()

    mocked_token_post.assert_called_once_with(
        "https://id.twitch.tv/oauth2/token",
        params={
            "client_id": twitch._client_id,
            "client_secret": twitch._client_secret,
            "grant_type": "client_credentials",
        },
    )
    assert twitch._access_token == FAKE_ACCESS_TOKEN
    assert twitch._access_token_expires == datetime.utcnow() + timedelta(seconds=EXPIRES_IN)


@freezegun.freeze_time()
async def test_ensure_token_generates_token_when_not_set(twitch: TwitchAPI, mocked_token_post):
    assert twitch._access_token is None
    assert twitch._access_token_expires is None

    await twitch._ensure_token()

    assert twitch._access_token == FAKE_ACCESS_TOKEN
    assert twitch._access_token_expires == datetime.utcnow() + timedelta(seconds=EXPIRES_IN)


@freezegun.freeze_time()
async def test_ensure_token_generates_token_when_expired(twitch: TwitchAPI, mocked_token_post):
    twitch._access_token = FAKE_ACCESS_TOKEN
    twitch._access_token_expires = datetime.utcnow() - timedelta(seconds=1)
    mocked_token_post.return_value = httpx.Response(200, json={"access_token": "new_token", "expires_in": EXPIRES_IN})

    await twitch._ensure_token()

    mocked_token_post.assert_called_once()
    assert twitch._access_token == "new_token"


@freezegun.freeze_time()
async def test_ensure_token_does_not_generate_token_when_not_expired(twitch: TwitchAPI, mocked_token_post):
    twitch._access_token = "test_token"
    twitch._access_token_expires = datetime.utcnow() + timedelta(seconds=1)

    await twitch._ensure_token()

    mocked_token_post.assert_not_called()
    assert twitch._access_token == "test_token"


from core.schemas.twitch import Game


async def test_cache_decorator_with_params(caplog, teardown_redis):
    @cache("test_cache", return_type=Game, params=["game_id", "game_name"])
    async def test_func(game_id="1", game_name="test_game"):
        return Game(id=game_id, name=game_name, box_art_url="")  # type: ignore

    with caplog.at_level(logging.DEBUG):
        result = await test_func(game_id="50")
        assert "Checking cache for key twitch:test_cache:50" in caplog.text
        assert result == Game(id="50", name="test_game", box_art_url="")

    with caplog.at_level(logging.DEBUG):
        result = await test_func(game_name="test_game2")
        assert "Checking cache for key twitch:test_cache:test_game2" in caplog.text
        assert result == Game(id="1", name="test_game2", box_art_url="")

    with pytest.raises(ValueError) as excinfo:
        await test_func(game_id="50", game_name="test_game2")  # type: ignore
        assert excinfo.value.args[0] == "Only onde parameter can be used as a key"


async def test_cache_decorator_without_params(caplog, teardown_redis):
    @cache("test_cache", return_type=Game, params=["game_id", "game_name"])
    async def test_func(game_id="1", game_name="test_game"):
        return Game(id=game_id, name=game_name, box_art_url="")  # type: ignore

    with caplog.at_level(logging.DEBUG):
        result = await test_func()
        assert "Checking cache for key twitch:test_cache" in caplog.text
        assert result == Game(id="1", name="test_game", box_art_url="")


async def test_cache_decorator_with_invalid_return_type(caplog, teardown_redis):
    @cache("test_cache", return_type=int)
    async def test_func():
        return "wololo"

    with pytest.raises(TypeError) as excinfo:
        with caplog.at_level(logging.WARNING):
            result = await test_func()
            assert result is None
            assert excinfo.value.args[0] == "Return type of test_func must be <class 'int'>"

    @cache("test_cache", return_type=None)
    async def test_func2():
        return "wololo"

    with pytest.raises(TypeError) as excinfo:
        with caplog.at_level(logging.WARNING):
            result = await test_func2()
            assert result is None
            assert excinfo.value.args[0] == "Return type must have a callable constructor"


async def test_cache_decorator_cache_hit(caplog, teardown_redis):
    @cache("test_cache", return_type=Game, params=["game_id", "game_name"])
    async def test_func(game_id="1", game_name="test_game"):
        return Game(id=game_id, name=game_name, box_art_url="")

    with caplog.at_level(logging.DEBUG):
        await test_func(game_id="50")
        assert "Checking cache for key twitch:test_cache:50" in caplog.text
        assert "test_cache not found in cache. Fetching from API" in caplog.text

    await asyncio.wait_for(*cache_tasks, timeout=5)

    with caplog.at_level(logging.DEBUG):
        result = await test_func(game_id="50")
        assert "Checking cache for key twitch:test_cache:50" in caplog.text
        assert "Cache hit: twitch:test_cache:50" in caplog.text
        assert result == Game(id="50", name="test_game", box_art_url="")


async def test_cache_decorator_with_none_result(caplog, teardown_redis):
    @cache("test_cache", return_type=Game)
    async def test_func():
        return None

    with caplog.at_level(logging.DEBUG):
        await test_func()
        assert "Checking cache for key twitch:test_cache" in caplog.text
        assert "test_cache not found in cache. Fetching from API" in caplog.text

    await asyncio.wait_for(*cache_tasks, timeout=5)

    with caplog.at_level(logging.DEBUG):
        result = await test_func()
        assert "Checking cache for key twitch:test_cache" in caplog.text
        assert "Cache hit: twitch:test_cache" in caplog.text
        assert result is None


from httpx import Response


async def test_get_success(twitch_authorized):
    path = "test_path"
    params = {"param1": "value1"}
    expected_url = f"https://api.twitch.tv/helix/{path}"
    expected_headers = {
        "Client-ID": twitch_authorized._client_id,
        "Authorization": f"Bearer {twitch_authorized._access_token}",
    }
    mock_response = httpx.Response(200, json={"data": "some_data"})
    mock_response.elapsed = timedelta(seconds=1)
    mock_response.request = httpx.Request("GET", expected_url, params=params, headers=expected_headers)

    with mock.patch.object(twitch_authorized._httpx_client, "get", return_value=mock_response) as mock_get:
        response = await twitch_authorized.get(path, params)

    mock_get.assert_called_once_with(expected_url, params=params, headers=expected_headers)
    assert response.json() == {"data": "some_data"}


async def test_get_http_error(twitch_authorized):
    path = "test_path"
    params = {"param1": "value1"}
    expected_url = f"https://api.twitch.tv/helix/{path}"
    mock_response = httpx.Response(404, json={"error": "not_found"})
    mock_response.elapsed = timedelta(seconds=1)
    mock_response.request = httpx.Request("GET", expected_url, params=params)

    with mock.patch.object(twitch_authorized._httpx_client, "get", return_value=mock_response):
        with pytest.raises(httpx.HTTPStatusError):
            await twitch_authorized.get(path, params)


async def test_post_success(twitch_authorized):
    path = "test_path"
    json_data = {"key": "value"}
    expected_url = f"https://api.twitch.tv/helix/{path}"
    expected_headers = {
        "Client-ID": twitch_authorized._client_id,
        "Authorization": f"Bearer {twitch_authorized._access_token}",
        "Content-Type": "application/json",
    }
    mock_response = httpx.Response(200, json={"result": "success"})
    mock_response.elapsed = timedelta(seconds=1)
    mock_response.request = httpx.Request("POST", expected_url, json=json_data, headers=expected_headers)

    with mock.patch.object(twitch_authorized._httpx_client, "post", return_value=mock_response) as mock_post:
        response = await twitch_authorized.post(path, json=json_data)

    mock_post.assert_called_once_with(expected_url, json=json_data, params=None, headers=expected_headers)
    assert response.json() == {"result": "success"}


async def test_post_http_error(twitch_authorized):
    path = "test_path"
    json_data = {"key": "value"}
    expected_url = f"https://api.twitch.tv/helix/{path}"
    mock_response = httpx.Response(500, json={"error": "internal_server_error"})
    mock_response.elapsed = timedelta(seconds=1)
    mock_response.request = httpx.Request("POST", expected_url, json=json_data)

    with mock.patch.object(twitch_authorized._httpx_client, "post", return_value=mock_response):
        with pytest.raises(httpx.HTTPStatusError):
            await twitch_authorized.post(path, json=json_data)


async def test_delete_success(twitch_authorized):
    path = "test_path"
    params = {"param1": "value1"}
    expected_url = f"https://api.twitch.tv/helix/{path}"
    expected_headers = {
        "Client-ID": twitch_authorized._client_id,
        "Authorization": f"Bearer {twitch_authorized._access_token}",
    }
    mock_response = httpx.Response(200, json={"result": "success"})
    mock_response.elapsed = timedelta(seconds=1)
    mock_response.request = httpx.Request("DELETE", expected_url, params=params, headers=expected_headers)

    with mock.patch.object(twitch_authorized._httpx_client, "delete", return_value=mock_response) as mock_delete:
        response = await twitch_authorized.delete(path, params)

    mock_delete.assert_called_once_with(expected_url, params=params, headers=expected_headers)
    assert response.status_code == 200


async def test_delete_http_error(twitch_authorized):
    path = "test_path"
    params = {"param1": "value1"}
    expected_url = f"https://api.twitch.tv/helix/{path}"
    mock_response = httpx.Response(403, json={"error": "forbidden"})
    mock_response.elapsed = timedelta(seconds=1)
    mock_response.request = httpx.Request("DELETE", expected_url, params=params)

    with mock.patch.object(twitch_authorized._httpx_client, "delete", return_value=mock_response):
        with pytest.raises(httpx.HTTPStatusError):
            await twitch_authorized.delete(path, params)
