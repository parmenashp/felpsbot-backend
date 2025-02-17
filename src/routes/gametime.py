from datetime import datetime, timezone
from typing import Annotated

import humanize
from fastapi import APIRouter, Depends
from fastapi.responses import PlainTextResponse
from loguru import logger

from core.dependencies.twitch import get_stream
from core.prisma import prisma
from core.schemas.twitch import Stream

router = APIRouter(tags=["Twitch Commands"])


@router.get("/streamgametime/{streamer_id}", summary="Time since the streamer started playing the current game.")
async def get_stream_game_time(
    stream: Annotated[Stream | None, Depends(get_stream)], fallback: str = "desconhecido"
) -> PlainTextResponse:
    """
    Returns the time since the streamer started playing the current game in a human readable format.
    Fallback is the text to be returned if the streamer is offline or the game is not known.
    Only works for the Felps channel (ID: 30672329) for now.
    """

    if not stream:
        logger.info("Streamer is offline, returning fallback")
        return PlainTextResponse(fallback)

    last_time = await prisma.lasttimeplayed.find_unique(
        where={"game_streamer_unique": {"game_id": int(stream.game_id), "streamer_id": int(stream.broadcaster_id)}}
    )

    if last_time is None:
        logger.info("Streamer is playing a game that is not in the database, returning fallback")
        return PlainTextResponse(fallback)

    time_playing_delta = datetime.now(timezone.utc) - last_time.last_time
    text = humanize.precisedelta(time_playing_delta, minimum_unit="seconds", format="%0.0f")

    logger.info(f"Streamer is playing {stream.game_name} for {text}")
    return PlainTextResponse(text)
