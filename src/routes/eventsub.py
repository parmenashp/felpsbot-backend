from fastapi import APIRouter, Depends, HTTPException, Request, Response, Security
from fastapi.responses import JSONResponse
from httpx import HTTPStatusError
from loguru import logger

from core import schemas
from core.dependencies.auth import authenticate_user
from core.dependencies.signature import verify_twitch_signature
from core.eventsub import eventsub
from core.models.eventsub import SubscriptionRequest

router = APIRouter(prefix="/eventsub", tags=["Twitch EventSub"])


# be sure to change the callback url in the core.constants file if you change the path here
@router.post(
    path="/callback",
    dependencies=[Depends(verify_twitch_signature)],
    summary="Callback endpoint for Twitch EventSub.",
)
async def eventsub_callback(request: Request):
    """
    This endpoint is called by Twitch when an event happens.
    """
    try:
        return await eventsub.callback_handler(request)
    except Exception as e:
        # Avoid interal server errors (500) to be returned to Twitch
        # That would cause Twitch to cancel the subscription in the future if it keeps failing

        # Reraise the intentional HTTPExceptions
        if isinstance(e, HTTPException):
            raise e

        logger.exception("Error while processing eventsub callback")
        return Response(status_code=200)


@router.get(
    path="/",
    response_model=list[schemas.eventsub.Subscription],
    dependencies=[Security(authenticate_user, scopes=["eventsub:list"])],
    summary="Returns a list of all Twitch EventSub subscriptions.",
)
async def list_subscriptions():
    await eventsub.fetch_subscriptions()
    return [x.to_dict() for x in eventsub.subscriptions]


@router.post(
    path="/",
    responses={
        202: {"description": "Subscription created"},
        409: {"description": "Subscription already exists"},
    },
    dependencies=[Security(authenticate_user, scopes=["eventsub:create"])],
    summary="Creates a new Twitch EventSub subscription.",
)
async def create_subscription(subscription: schemas.SubscriptionCreate):
    """
    The subscription type must be one of: `channel.update`, `stream.online`, `stream.offline`
    """
    match subscription.type:
        case "channel.update":
            request = SubscriptionRequest.channel_update(broadcaster_user_id=subscription.broadcaster_user_id)
        case "stream.online":
            request = SubscriptionRequest.stream_online(broadcaster_user_id=subscription.broadcaster_user_id)
        case "stream.offline":
            request = SubscriptionRequest.stream_offline(broadcaster_user_id=subscription.broadcaster_user_id)
        case _:
            raise HTTPException(
                status_code=400,
                detail="Invalid subscription type, must be one of: channel.update, stream.online, stream.offline",
            )
    try:
        eventsub_response = await eventsub.subscribe(request)  # type: ignore
        if eventsub_response:
            return JSONResponse(content=eventsub_response)
        else:
            raise HTTPException(status_code=409, detail="The subscription already exists")
    except HTTPStatusError as e:
        raise HTTPException(status_code=e.response.status_code, detail=e.response.json().get("message"))


@router.delete(
    path="/",
    responses={204: {"description": "Subscription deleted"}, 404: {"description": "Subscription not found"}},
    dependencies=[Security(authenticate_user, scopes=["eventsub:delete"])],
    summary="Deletes a Twitch EventSub subscription.",
)
async def delete_subscription(id: str):
    await eventsub.fetch_subscriptions()
    for subscription in eventsub.subscriptions:
        if subscription.id == id:
            await eventsub.unsubscribe(subscription)
            return Response(status_code=204)

    raise HTTPException(status_code=404, detail="Subscription not found")
