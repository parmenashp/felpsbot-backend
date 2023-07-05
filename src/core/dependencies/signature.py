import hashlib
import hmac
import os

from fastapi import HTTPException, Request
from loguru import logger


async def _verify_signature(request: Request) -> bool:
    """Verify the signature of a Twitch EventSub callback request."""
    expected = request.headers["Twitch-Eventsub-Message-Signature"]
    hmac_message = (
        request.headers["Twitch-Eventsub-Message-Id"]
        + request.headers["Twitch-Eventsub-Message-Timestamp"]
        + (await request.body()).decode("UTF-8")
    )
    sig = (
        "sha256="
        + hmac.new(
            bytes(os.environ["EVENTSUB_SECRET_KEY"], "utf-8"),
            msg=bytes(hmac_message, "utf-8"),
            digestmod=hashlib.sha256,
        )
        .hexdigest()
        .lower()
    )
    return sig == expected


async def verify_twitch_signature(request: Request):
    """Dependency to verify the signature of a Twitch EventSub callback request."""
    try:
        if not await _verify_signature(request):
            logger.warning("Invalid Twitch EventSub signature")
            raise HTTPException(status_code=401, detail="Invalid signature")
    except KeyError:
        logger.info("Missing Twitch EventSub signature")
        raise HTTPException(status_code=400, detail="Missing signature")
