from typing import Annotated

from typing import List

from fastapi import APIRouter, HTTPException, Query, Security
from fastapi.responses import JSONResponse

from core.schemas.twitch import Game as TwitchGame

from core.dependencies.auth import authenticate_user
from core.prisma import prisma
from core.twitch import twitch_api

router = APIRouter(prefix="/games", tags=["Games"])


@router.get(
    "/search",
    summary="Search games (Twitch categories)",
    description="Returns a list of games matching the query using Twitch Search Categories API.",
    responses={
        200: {
            "description": "List of games",
            "content": {
                "application/json": {
                    "example": [
                        {"id": 123, "name": "Minecraft", "imageUrl": "https://.../{width}x{height}.jpg"}
                    ]
                }
            },
        },
        400: {"description": "Query is required"},
        401: {"description": "Not authenticated"},
        403: {"description": "Not enough permissions"},
    },
)
async def search_games(
    query: Annotated[str | None, Query(min_length=1)] = None,
    _: Annotated[None, Security(authenticate_user, scopes=["subscriptions:read"])] = None,
):
    if not query:
        raise HTTPException(status_code=400, detail="Query is required")
    games = await twitch_api.search_games(query=query, limit=25)
    game_ids = [int(g.id) for g in games]
    last_times = {}
    if game_ids:
        db_last_times = await prisma.lasttimeplayed.find_many(
            where={
                "streamer_id": 30672329,
                "game_id": {"in": game_ids},
            }
        )
        last_times = {int(x.game_id): x.last_time.isoformat() for x in db_last_times}

    return JSONResponse(
        [
            {
                "id": int(g.id),
                "name": g.name,
                "imageUrl": g.box_art_url,
                "lastTimePlayed": last_times.get(int(g.id)),
            }
            for g in games
        ]
    )


