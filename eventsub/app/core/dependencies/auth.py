import json
import os
from urllib.request import urlopen

import httpx
from app.core.constants import AUTH0_AUDIENCE, AUTH0_ISSUER
from app.core.schemas import auth0
from authlib.jose import JWTClaims, jwt
from authlib.jose.errors import ExpiredTokenError, JoseError
from authlib.jose.rfc7517.jwk import JsonWebKey
from authlib.oauth2.rfc7523 import JWTBearerTokenValidator
from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from loguru import logger
from starlette.status import HTTP_403_FORBIDDEN, HTTP_429_TOO_MANY_REQUESTS

token_auth_scheme = HTTPBearer()


class Auth0JWTBearerTokenValidator(JWTBearerTokenValidator):
    def __init__(self, issuer, audience):
        jsonurl = urlopen(f"{issuer}.well-known/jwks.json")
        public_key = JsonWebKey.import_key_set(json.loads(jsonurl.read()))
        super(Auth0JWTBearerTokenValidator, self).__init__(public_key)
        self.claims_options = {
            "exp": {"essential": True},
            "aud": {"essential": True, "value": audience},
            "iss": {"essential": True, "value": issuer},
        }

    async def authenticate_token(self, token_string) -> JWTClaims:
        logger.debug("Validating auth token")
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
            raise HTTPException(status_code=HTTP_403_FORBIDDEN, detail="Access token expired")
        except JoseError:
            logger.info(f"Unable to validate token, refusing access")
            raise HTTPException(status_code=HTTP_403_FORBIDDEN, detail="Invalid token")


token_validator = Auth0JWTBearerTokenValidator(audience=AUTH0_AUDIENCE, issuer=AUTH0_ISSUER)


class AuthenticatedJWTToken:
    def __init__(self, claims: JWTClaims, token: str) -> None:
        self.claims = claims
        self.token = token
        # Exemple {"sub": "oauth2|discord|182575852406571008"}
        self.discord_id = int(claims["sub"].split("|")[2])


async def authenticate_user(
    token: HTTPAuthorizationCredentials = Depends(token_auth_scheme),
) -> AuthenticatedJWTToken:
    claims = await token_validator.authenticate_token(token.credentials)
    return AuthenticatedJWTToken(claims, token.credentials)


async def get_current_user_id(token: AuthenticatedJWTToken = Depends(authenticate_user)) -> int:
    """Dependency to get the current user discord id from the auth0 access token"""
    return token.discord_id


class UserHasScope:
    """Dependency to check if the current user has the required scope"""

    def __init__(self, required_scope: str) -> None:
        self.required_scope = required_scope

    def __call__(self, token: AuthenticatedJWTToken = Depends(authenticate_user)) -> None:
        scopes = token.claims.get("scope", "").split()
        if self.required_scope not in scopes:
            raise HTTPException(
                status_code=HTTP_403_FORBIDDEN, detail=f"You don't have the required scope: {self.required_scope}"
            )


def get_current_auth0_user(token: AuthenticatedJWTToken = Depends(authenticate_user)) -> auth0.User:
    """Dependency to get the current user info from the Auth0 token"""
    r = httpx.get(
        # https://felpsbot.us.auth0.com/userinfo
        f"{os.environ['AUTH0_ISSUER']}userinfo",
        headers={"Authorization": f"Bearer {token.token}", "Content-Type": "application/json"},
    )
    try:
        r.raise_for_status()
    except httpx.HTTPStatusError as e:
        logger.debug(f"Failed to get user info from Auth0: {e}")
        raise HTTPException(status_code=HTTP_429_TOO_MANY_REQUESTS, detail="Too many requests")
    return auth0.User(discord_id=str(token.discord_id), **r.json())
