from core.schemas.twitch import Channel
from core.twitch import twitch_api
from fastapi import HTTPException, Path
from httpx import HTTPStatusError


async def get_channel(streamer_id: int = Path(description="The ID of the streamer", ge=1, le=2147483647)) -> Channel:
    # the streamer_id has the max value of int32
    try:
        return await twitch_api.get_channel(streamer_id)
    except HTTPStatusError as e:
        if e.response.status_code == 500:
            raise HTTPException(503, "Twitch API error")
        else:
            raise e

    except IndexError:
        raise HTTPException(status_code=404, detail="Streamer not found")
