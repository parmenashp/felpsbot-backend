from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Security
from fastapi.responses import JSONResponse, Response
from loguru import logger

from core.dependencies.auth import authenticate_user, get_current_user_id
from core.prisma import prisma
from core.twitch import twitch_api
from core.schemas.subscriptions import (
    CreateSubscriptionRequest,
    SubscriptionCreated,
    SubscriptionItem,
)
from prisma import errors as prisma_errors

router = APIRouter(prefix="/subscriptions", tags=["Subscriptions"])


@router.get(
    "/",
    summary="List subscriptions",
    description=(
        "Returns the list of games the authenticated user is subscribed to for the Felps streamer (ID 30672329)."
    ),
    response_model=list[SubscriptionItem],
    responses={
        200: {"description": "List of subscriptions"},
        401: {"description": "Not authenticated"},
        403: {"description": "Not enough permissions"},
    },
)
async def list_subscriptions(
    user_id: Annotated[int, Depends(get_current_user_id)],
    _: Annotated[None, Security(authenticate_user, scopes=["subscriptions:read"])] = None,
):
    """List all game subscriptions for the current user for the Felps streamer."""
    logger.info(f"Listing subscriptions for user {user_id}")
    subscriptions = await prisma.gamesubscription.find_many(
        where={
            "user_discord_id": user_id,
            # Streamer hardcoded to Felps (matches bot settings)
            "streamer_twitch_id": 30672329,
        },
        include={"game": True},
        order={"created_at": "asc"},
    )
    result = [
        SubscriptionItem(
            gameId=int(s.game_twitch_id),
            name=s.game.name if s.game else None,
            imageUrl=s.game.image_url if s.game else None,
            createdAt=s.created_at.isoformat() if getattr(s, "created_at", None) else None,
        )
        for s in subscriptions
    ]
    return result


@router.post(
    "/",
    summary="Create subscription",
    description=(
        "Creates a subscription to a game for the authenticated user. "
        "Provide exactly one of gameId or gameName. Upserts User and Game before creating the subscription."
    ),
    response_model=SubscriptionCreated,
    responses={
        201: {"description": "Subscription created"},
        400: {"description": "Bad request"},
        401: {"description": "Not authenticated"},
        403: {"description": "Not enough permissions"},
        404: {"description": "Game not found"},
        409: {"description": "Subscription already exists"},
    },
)
async def create_subscription(
    body: CreateSubscriptionRequest,
    user_id: Annotated[int, Depends(get_current_user_id)],
    _: Annotated[None, Security(authenticate_user, scopes=["subscriptions:write"])] = None,
):
    """Create a game subscription for the current user. Accepts either gameId or gameName."""
    game_id = body.gameId
    game_name = body.gameName

    # Resolve game by id or name via Twitch API
    if game_name:
        games = await twitch_api.get_games(game_names=[game_name])
        if not games:
            raise HTTPException(status_code=404, detail="Game not found")
        game = games[0]
        game_id = int(game.id)
        game_name = game.name
        image_url = game.box_art_url
    else:
        games = await twitch_api.get_games(game_ids=[str(game_id)])
        if not games:
            raise HTTPException(status_code=404, detail="Game not found")
        game = games[0]
        game_id = int(game.id)
        game_name = game.name
        image_url = game.box_art_url

    # Upsert user and game, then create subscription
    await prisma.user.upsert(
        where={"discord_id": user_id},
        data={"create": {"discord_id": user_id, "name": str(user_id)}, "update": {}},
    )
    await prisma.game.upsert(
        where={"twitch_id": game_id},
        data={
            "create": {"twitch_id": game_id, "name": game_name, "image_url": image_url},
            "update": {"name": game_name, "image_url": image_url},
        },
    )
    try:
        await prisma.gamesubscription.create(
            data={
                "user_discord_id": user_id,
                "game_twitch_id": game_id,
                "streamer_twitch_id": 30672329,
            }
        )
    except prisma_errors.UniqueViolationError as e:
        logger.debug(f"Unique violation on subscription create: {e}")
        raise HTTPException(status_code=409, detail="Subscription already exists")

    return JSONResponse(SubscriptionCreated(gameId=game_id, name=game_name, imageUrl=image_url).dict(), status_code=201)


@router.delete(
    "/{game_id}",
    summary="Delete subscription",
    description="Deletes the subscription for the given game for the authenticated user (Felps streamer).",
    responses={
        204: {"description": "Subscription deleted"},
        401: {"description": "Not authenticated"},
        403: {"description": "Not enough permissions"},
        404: {"description": "Subscription not found"},
    },
)
async def delete_subscription(
    game_id: int,
    user_id: Annotated[int, Depends(get_current_user_id)],
    _: Annotated[None, Security(authenticate_user, scopes=["subscriptions:write"])] = None,
):
    """Delete a game subscription for the current user for the Felps streamer."""
    try:
        await prisma.gamesubscription.delete(
            where={
                "user_game_streamer_unique": {
                    "user_discord_id": user_id,
                    "game_twitch_id": int(game_id),
                    "streamer_twitch_id": 30672329,
                }
            }
        )
    except prisma_errors.RecordNotFoundError:
        raise HTTPException(status_code=404, detail="Subscription not found")
    return Response(status_code=204)


