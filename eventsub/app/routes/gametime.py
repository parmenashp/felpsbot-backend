from datetime import datetime

import humanize
from app.core.dependencies.twitch import get_channel
from app.core.models.database import LastTimePlayed
from app.core.schemas.twitch import Channel
from fastapi import APIRouter, Depends
from fastapi.responses import PlainTextResponse

router = APIRouter()


@router.get("/streamgametime/{streamer_id}")
async def get_stream_game_time(channel: Channel = Depends(get_channel)):

    last_time = await LastTimePlayed.from_database(channel.broadcaster_id, channel.game_id)

    if last_time is None:
        return PlainTextResponse("algum tempo")

    time_playing_delta = datetime.now() - last_time.last_played
    text = humanize.precisedelta(time_playing_delta, minimum_unit="minutes")

    return PlainTextResponse(text)
