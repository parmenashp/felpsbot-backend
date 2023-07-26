from datetime import datetime, timezone

import humanize
from fastapi import APIRouter, Depends
from fastapi.responses import PlainTextResponse

from core.prisma import prisma
from core.dependencies.twitch import get_channel
from core.schemas.twitch import Channel

router = APIRouter(tags=["Twitch Commands"])


@router.get("/streamgametime/{streamer_id}", summary="Time since the streamer started playing the current game.")
async def get_stream_game_time(
    fallback: str = "desconhecido", channel: Channel = Depends(get_channel)
) -> PlainTextResponse:
    """
    Returns the time since the streamer started playing the current game in a human readable format.
    Fallback is the text to be returned if the streamer is offline or the game is not known.
    It only works for the Felps channel (ID: 30672329) for now.
    """

    # If streamer offline, game_id = ""
    if not channel.game_id:
        return PlainTextResponse(fallback)

    last_time = await prisma.lasttimeplayed.find_unique(
        where={"game_streamer_unique": {"game_id": channel.game_id, "streamer_id": channel.broadcaster_id}}
    )

    if last_time is None:
        return PlainTextResponse(fallback)

    time_playing_delta = datetime.now(timezone.utc) - last_time.last_time
    text = humanize.precisedelta(time_playing_delta, minimum_unit="seconds", format="%0.0f")

    return PlainTextResponse(text)
