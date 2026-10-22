"""Auth boundary tests: local JWKS verification, remote fallback, outage handling."""

import httpx
import pytest
from fastapi import HTTPException
from jose import JWTError

from lingforge.security import auth
from lingforge.security.auth import current_user_id


class _FakeRequest:
    def __init__(self, authorization: str = "") -> None:
        self.headers = {"authorization": authorization} if authorization else {}


class _DummyClient:
    """Stand-in httpx client; tests stub the network at the auth module boundary."""

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_args):
        return False


@pytest.fixture(autouse=True)
def _no_real_http_client(monkeypatch: pytest.MonkeyPatch) -> None:
    """The test machine's SOCKS proxy breaks real client construction; never build one."""
    monkeypatch.setattr(httpx, "AsyncClient", lambda timeout: _DummyClient())


@pytest.mark.anyio
async def test_missing_bearer_token_is_401() -> None:
    with pytest.raises(HTTPException) as exc_info:
        await current_user_id(_FakeRequest())  # type: ignore[arg-type]
    assert exc_info.value.status_code == 401


@pytest.mark.anyio
async def test_local_jwks_verification_avoids_remote_call(monkeypatch: pytest.MonkeyPatch) -> None:
    """Steady state: a cached JWKS verifies tokens locally, no Auth round-trip."""
    async def fake_jwks(_client):
        return {"keys": [{"kid": "k1", "alg": "ES256"}]}

    monkeypatch.setattr(auth, "_jwks", fake_jwks)
    monkeypatch.setattr(auth.jwt, "get_unverified_header", lambda _token: {"kid": "k1"})
    monkeypatch.setattr(auth.jwt, "decode", lambda *_args, **_kwargs: {"sub": "user-1"})
    assert await current_user_id(_FakeRequest("Bearer good")) == "user-1"  # type: ignore[arg-type]


@pytest.mark.anyio
async def test_invalid_signature_is_401(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_jwks(_client):
        return {"keys": [{"kid": "k1", "alg": "ES256"}]}

    def reject(*_args, **_kwargs):
        raise JWTError("bad signature")

    monkeypatch.setattr(auth, "_jwks", fake_jwks)
    monkeypatch.setattr(auth.jwt, "get_unverified_header", lambda _token: {"kid": "k1"})
    monkeypatch.setattr(auth.jwt, "decode", reject)
    with pytest.raises(HTTPException) as exc_info:
        await current_user_id(_FakeRequest("Bearer bad"))  # type: ignore[arg-type]
    assert exc_info.value.status_code == 401


@pytest.mark.anyio
async def test_supabase_outage_is_503_not_500(monkeypatch: pytest.MonkeyPatch) -> None:
    """Both JWKS and remote fallback unreachable: handled 503, never an unhandled 500."""

    class TimeoutClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return False

        async def get(self, *_args, **_kwargs):
            raise httpx.ConnectTimeout("timed out")

    monkeypatch.setattr(auth, "_jwks_cache", None)
    monkeypatch.setattr(httpx, "AsyncClient", lambda timeout: TimeoutClient())
    with pytest.raises(HTTPException) as exc_info:
        await current_user_id(_FakeRequest("Bearer token"))  # type: ignore[arg-type]
    assert exc_info.value.status_code == 503
