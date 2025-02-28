from datetime import datetime, timezone
from typing import Annotated

import humanize
from fastapi import APIRouter, Depends
from fastapi.responses import PlainTextResponse
from loguru import logger

from core.dependencies import twitch
from core.prisma import prisma
from core.schemas.twitch import Stream

router = APIRouter(tags=["Twitch Commands"])


@router.get("/streamgametime/{streamer_id}", summary="Time since the streamer started playing the current game.")
async def get_stream_game_time(
    stream: Annotated[Stream | None, Depends(twitch.get_stream)],
    streamer_id: int,
    offline: str = "{streamer} está offline.",
    online: str = "{streamer} está jogando {game} há {duration}.",
    unknown: str = "{streamer} está jogando {game} há um tempo desconhecido.",
    error: str = "Ocorreu um erro ao buscar informações do streamer.",
) -> PlainTextResponse:
    """
    Returns the time since the streamer started playing the current game in a human readable format.

    Parameters:
    - streamer_id (path): The Twitch ID of the streamer to check
    - offline (query, optional): Custom message for offline status. Available formats:
        - {streamer}: Streamer's display name
    - online (query, optional): Custom message for online status. Available formats:
        - {streamer}: Streamer's display name
        - {game}: Current game name
        - {duration}: Time playing the current game
    - unknown (query, optional): Custom message when game time is unknown. Available formats:
        - {streamer}: Streamer's display name
        - {game}: Current game name
    - error (query, optional): Custom error message.

    Returns:
    - A plain text response with the formatted message based on streamer's status

    Examples:
    - /streamgametime/30672329
    - /streamgametime/30672329?offline=Streamer {streamer} is offline
    - /streamgametime/30672329?online={streamer} has been playing {game} for {duration}
    """
    try:
        if not stream:
            logger.info("Streamer is offline, returning fallback")
            channel = await twitch.get_channel(streamer_id)
            return PlainTextResponse(offline.format(streamer=channel.broadcaster_name))

        last_time = await prisma.lasttimeplayed.find_unique(
            where={"game_streamer_unique": {"game_id": int(stream.game_id), "streamer_id": int(stream.user_id)}}
        )

        if last_time is None:
            logger.info("Streamer is playing a game that is not in the database, returning unknown message")
            return PlainTextResponse(unknown.format(streamer=stream.user_name, game=stream.game_name))

        time_playing_delta = datetime.now(timezone.utc) - last_time.last_time
        duration = humanize.precisedelta(time_playing_delta, minimum_unit="seconds", format="%0.0f")

        logger.info(f"Streamer is playing {stream.game_name} for {duration}")
        return PlainTextResponse(online.format(streamer=stream.user_name, game=stream.game_name, duration=duration))

    except Exception as e:
        logger.exception(f"Error getting stream game time: {e}")
        return PlainTextResponse(error)
