from datetime import datetime, timezone

import humanize
from fastapi import APIRouter, Depends
from fastapi.responses import PlainTextResponse

from core.prisma import prisma
from core.dependencies.twitch import get_channel
from core.schemas.twitch import Channel

router = APIRouter()


@router.get("/streamgametime/{streamer_id}")
async def get_stream_game_time(
    fallback: str = "desconhecido", channel: Channel = Depends(get_channel)
) -> PlainTextResponse:
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
