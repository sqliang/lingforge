"""Supabase access-token verification at the FastAPI trust boundary.

Verification is local-first: the project's JWKS is fetched once and cached, so steady
state requests cost a local signature check instead of a remote Auth round-trip (which
measured multiple seconds on slow networks). The remote user endpoint remains as the
fallback for JWKS fetch failures and legacy key setups.

A Supabase outage must surface as a handled 503, not an unhandled 500: handled
responses pass through CORSMiddleware, while unhandled ones reach the browser
without CORS headers and masquerade as cross-origin failures.
"""

import time
from typing import Annotated, Any

import httpx
from fastapi import Depends, HTTPException, Request, status
from jose import JWTError, jwt

from lingforge.settings import settings

_JWKS_CACHE_TTL_SECONDS = 600
_jwks_cache: tuple[float, dict[str, Any]] | None = None


async def _jwks(client: httpx.AsyncClient) -> dict[str, Any]:
    """Fetch and cache the project's signing keys; rotation is rare and handled by TTL."""
    global _jwks_cache
    now = time.monotonic()
    if _jwks_cache and now - _jwks_cache[0] < _JWKS_CACHE_TTL_SECONDS:
        return _jwks_cache[1]
    response = await client.get(
        f"{settings.supabase_url}/auth/v1/.well-known/jwks.json",
        headers={"apikey": settings.supabase_anon_key},
    )
    response.raise_for_status()
    _jwks_cache = (now, response.json())
    return _jwks_cache[1]


def _verify_locally(token: str, keys: dict[str, Any]) -> str:
    """Verify the JWT against the JWKS and return the user id (sub claim)."""
    kid = jwt.get_unverified_header(token).get("kid")
    key = next((candidate for candidate in keys.get("keys", []) if candidate.get("kid") == kid), None)
    if not key:
        raise JWTError("Unknown signing key")
    claims = jwt.decode(token, key, algorithms=[key.get("alg", "ES256")], audience="authenticated")
    return str(claims["sub"])


async def _verify_remotely(client: httpx.AsyncClient, authorization: str) -> str:
    """Fallback to Supabase Auth's user endpoint when local verification is unavailable."""
    try:
        response = await client.get(
            f"{settings.supabase_url}/auth/v1/user",
            headers={"Authorization": authorization, "apikey": settings.supabase_anon_key},
        )
    except httpx.HTTPError:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Auth service temporarily unavailable")
    if response.status_code != 200:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid session")
    return response.json()["id"]


async def current_user_id(request: Request) -> str:
    """Resolve the caller with Supabase Auth; never trust a browser-supplied user id."""
    authorization = request.headers.get("authorization", "")
    if not authorization.startswith("Bearer "):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing bearer token")
    token = authorization.removeprefix("Bearer ").strip()
    async with httpx.AsyncClient(timeout=5) as client:
        try:
            keys = await _jwks(client)
        except httpx.HTTPError:
            # JWKS unreachable: degrade to the remote endpoint rather than failing open.
            return await _verify_remotely(client, authorization)
        try:
            return _verify_locally(token, keys)
        except JWTError:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid session")


CurrentUserId = Annotated[str, Depends(current_user_id)]
