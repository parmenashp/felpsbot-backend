from datetime import datetime, timezone

import humanize
from app.core.dependencies.twitch import get_channel
from app.core.models.database import LastTimePlayed
from app.core.schemas.twitch import Channel
from fastapi import APIRouter, Depends
from fastapi.responses import PlainTextResponse

router = APIRouter()


@router.get("/streamgametime/{streamer_id}")
async def get_stream_game_time(fallback: str = "desconhecido", channel: Channel = Depends(get_channel)):

    # If streamer offline, game_id = ""
    if not channel.game_id:
        return PlainTextResponse(fallback)

    last_time = await LastTimePlayed.from_database(channel.broadcaster_id, channel.game_id)

    if last_time is None:
        return PlainTextResponse(fallback)

    time_playing_delta = datetime.now(timezone.utc) - last_time.last_played
    text = humanize.precisedelta(time_playing_delta, minimum_unit="minutes")

    return PlainTextResponse(text)
