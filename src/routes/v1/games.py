from typing import Annotated

from typing import List

from fastapi import APIRouter, HTTPException, Query, Security
from fastapi.responses import JSONResponse

from core.schemas.twitch import Game as TwitchGame

from core.dependencies.auth import authenticate_user
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
    return JSONResponse(
        [
            {
                "id": int(g.id),
                "name": g.name,
                "imageUrl": g.box_art_url,
            }
            for g in games
        ]
    )


