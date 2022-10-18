from app.core.schemas.twitch import Channel
from app.core.twitch import twitch_api
from fastapi import HTTPException


async def get_channel(streamer_id: int) -> Channel:
    channel = await twitch_api.fetch_channels([streamer_id])
    try:
        return channel[0]
    except IndexError:
        raise HTTPException(status_code=404, detail="Streamer not found")
