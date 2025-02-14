import json
import urllib.parse
from typing import Annotated, Optional

import httpx
from authlib.jose import JWTClaims, jwt
from authlib.jose.errors import ExpiredTokenError, JoseError
from authlib.jose.rfc7517.jwk import JsonWebKey
from authlib.oauth2.rfc7523 import JWTBearerTokenValidator
from fastapi import Depends, HTTPException, Request
from fastapi.openapi.models import OAuthFlowImplicit, OAuthFlows
from fastapi.security import OAuth2, SecurityScopes
from loguru import logger
from starlette.status import (
    HTTP_401_UNAUTHORIZED,
    HTTP_403_FORBIDDEN,
    HTTP_429_TOO_MANY_REQUESTS,
    HTTP_503_SERVICE_UNAVAILABLE,
)

from core.schemas import auth0
from core.settings import settings


class DiscordOAuth2ImplicitBearer(OAuth2):
    def __init__(self):
        url_encoded_audience = urllib.parse.urlencode({"audience": settings.auth0_audience})
        authorization_url = f"{settings.auth0_issuer}authorize?{url_encoded_audience}&connection=discord"
        super().__init__(
            flows=OAuthFlows(
                implicit=OAuthFlowImplicit(
                    authorizationUrl=authorization_url,
                    scopes={
                        "openid": "OpenID",
                        "profile": "Profile",
                        "eventsub:list": "List EventSub subscriptions",
                        "eventsub:create": "Create EventSub subscriptions",
                        "eventsub:delete": "Delete EventSub subscriptions",
                    },
                )
            ),
            scheme_name="Auth0 Discord",
            description="Connect with Discord to authenticate using Auth0",
            auto_error=True,
        )

    async def __call__(self, request: Request) -> Optional[str]:
        authorization = request.headers.get("Authorization")
        if authorization:
            scheme, _, param = authorization.partition(" ")
            if scheme.lower() == "bearer":
                return param
        if self.auto_error:
            raise HTTPException(
                status_code=HTTP_401_UNAUTHORIZED,
                detail="Not authenticated",
                headers={"WWW-Authenticate": "Bearer"},
            )
        return None


class Auth0JWTBearerTokenValidator(JWTBearerTokenValidator):
    def __init__(self, issuer, audience):
        jsonurl = httpx.get(f"{issuer}.well-known/jwks.json")
        public_key = JsonWebKey.import_key_set(json.loads(jsonurl.read()))
        super(Auth0JWTBearerTokenValidator, self).__init__(public_key)
        self.claims_options = {
            "exp": {"essential": True},
            "aud": {"essential": True, "value": audience},
            "iss": {"essential": True, "value": issuer},
        }

    async def authenticate_token(self, token_string) -> JWTClaims:
        logger.debug("Validating auth token")
        credentials_exception = HTTPException(
            status_code=HTTP_401_UNAUTHORIZED,
            detail="Invalid token",
            headers={"WWW-Authenticate": "Bearer"},
        )
        try:
            claims = jwt.decode(
                token_string,
                self.public_key,
                claims_options=self.claims_options,
                claims_cls=self.token_cls,
            )
            claims.validate()
            return claims
        except ExpiredTokenError:
            logger.info("Access token expired")
            raise credentials_exception
        except JoseError:
            logger.info(f"Unable to validate token, refusing access")
            raise credentials_exception


class AuthenticatedJWTToken:
    def __init__(self, claims: JWTClaims, token: str) -> None:
        self.claims = claims
        self.token = token
        self.scopes: list[str] = claims.get("scope", "").split()

        # Exemple discord {"sub": "oauth2|discord|182575852406571008"}
        if claims["sub"].startswith("oauth2|discord|"):
            self.discord_id = int(claims["sub"].split("|")[2])
        else:
            raise HTTPException(status_code=HTTP_403_FORBIDDEN, detail="Account not linked with Discord")


implicit_auth_scheme = DiscordOAuth2ImplicitBearer()
token_validator = Auth0JWTBearerTokenValidator(audience=settings.auth0_audience, issuer=settings.auth0_issuer)


async def authenticate_user(
    security_scopes: SecurityScopes, token: Annotated[str, Depends(implicit_auth_scheme)]
) -> AuthenticatedJWTToken:
    """Authenticates the user using the auth0 access token and validates the scopes."""
    if security_scopes.scopes:
        authenticate_value = f'Bearer scope="{security_scopes.scope_str}"'
    else:
        authenticate_value = "Bearer"

    claims = await token_validator.authenticate_token(token)
    token_scopes = claims.get("scope", "").split()
    logger.info(f"token_scopes: {token_scopes}, security_scopes: {security_scopes.scopes}")
    for scope in security_scopes.scopes:
        if scope not in token_scopes:
            raise HTTPException(
                status_code=HTTP_403_FORBIDDEN,
                detail="Not enough permissions",
                headers={"WWW-Authenticate": authenticate_value},
            )
    return AuthenticatedJWTToken(claims, token)


async def get_current_user_id(token: Annotated[AuthenticatedJWTToken, Depends(authenticate_user)]) -> int:
    """Dependency to get the current user discord id from the auth0 access token"""

    return token.discord_id


async def get_current_auth0_user(token: Annotated[AuthenticatedJWTToken, Depends(authenticate_user)]) -> auth0.User:
    """Dependency to get the current user info from the Auth0 token."""

    async with httpx.AsyncClient() as client:
        r = await client.get(
            url=f"{settings.auth0_issuer}userinfo",
            headers={"Authorization": f"Bearer {token.token}", "Content-Type": "application/json"},
        )
    try:
        r.raise_for_status()
    except httpx.HTTPStatusError as e:
        logger.debug(f"Failed to get user info from Auth0: {e}")
        if e.response.status_code == HTTP_429_TOO_MANY_REQUESTS:
            raise HTTPException(status_code=HTTP_429_TOO_MANY_REQUESTS, detail="Too many requests")
        raise HTTPException(status_code=HTTP_503_SERVICE_UNAVAILABLE, detail="Auth0 is unavailable")
    except httpx.HTTPError as e:
        logger.debug(f"Failed to get user info from Auth0: {e}")
        raise HTTPException(status_code=HTTP_503_SERVICE_UNAVAILABLE, detail="Auth0 is unavailable")

    return auth0.User(discord_id=str(token.discord_id), **r.json())
