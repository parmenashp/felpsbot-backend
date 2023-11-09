from typing import Annotated

from loguru import logger
from core.schemas.twitch import Channel
from core.twitch import twitch_api
from fastapi import HTTPException, Path
from httpx import HTTPStatusError


async def get_channel(
    streamer_id: Annotated[int, Path(description="The ID of the streamer", ge=1, le=2147483647)]
    # the streamer_id has the max value of int32
) -> Channel:
    """
    Get the Twitch channel information for the given streamer ID.

    Args:
        streamer_id (int): The ID of the streamer.

    Returns:
        Channel: The Twitch channel information for the given streamer ID.

    Raises:
        HTTPException: If the streamer is not found or if there is an error with the Twitch API.
    """
    try:
        channel = await twitch_api.get_channel(streamer_id)
        if not channel:
            logger.info(f"Streamer {streamer_id} not found")
            raise HTTPException(status_code=404, detail="Streamer not found")
        return channel

    except HTTPStatusError as e:
        logger.exception("Twitch API error")
        if e.response.status_code == 500:
            raise HTTPException(503, "Twitch API error")
        else:
            raise e
