from app.core.schemas.twitch import Channel
from app.core.twitch import twitch_api
from fastapi import HTTPException, Path
from httpx import HTTPStatusError


async def get_channel(streamer_id: int = Path("The ID of the streamer", ge=1, le=2147483647)) -> Channel:
    # the streamer_id has the max value of int32
    try:
        channel = await twitch_api.fetch_channels([streamer_id])
        return channel[0]
    except HTTPStatusError as e:
        if e.response.status_code == 500:
            raise HTTPException(503, "Twitch API error")
        else:
            raise e

    except IndexError:
        raise HTTPException(status_code=404, detail="Streamer not found")
