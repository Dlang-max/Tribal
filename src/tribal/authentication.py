"""GitHub browser login for the management app and shared identity helpers."""

from __future__ import annotations

import hmac
import secrets
from dataclasses import dataclass
from typing import Any
from urllib.parse import urljoin

import httpx
from authlib.integrations.starlette_client import OAuth
from authlib.integrations.base_client.errors import OAuthError
from fastapi import APIRouter, Header, HTTPException, Request
from fastapi.responses import RedirectResponse
from starlette.middleware.sessions import SessionMiddleware

from tribal.settings import Settings, SettingsError

_SESSION_IDENTITY_KEY = "github_identity"
_SESSION_CSRF_KEY = "csrf_token"


@dataclass(frozen=True, slots=True)
class GitHubIdentity:
    """Verified GitHub account fields safe for Tribal's local authorization decisions."""

    github_id: int
    login: str
    name: str | None = None
    email: str | None = None

    def as_session_value(self) -> dict[str, Any]:
        return {"github_id": self.github_id, "login": self.login, "name": self.name, "email": self.email}


def add_management_session_middleware(app: Any, settings: Settings) -> None:
    """Add signed, HTTP-only browser sessions to a management FastAPI app."""
    if not settings.session_signing_key:
        raise SettingsError("SESSION_SIGNING_KEY must be set for management browser sessions")
    app.add_middleware(
        SessionMiddleware,
        secret_key=settings.session_signing_key,
        session_cookie="tribal_session",
        same_site="lax",
        https_only=settings.public_base_url.startswith("https://"),
        max_age=60 * 60 * 12,
    )


def _identity_from_session(request: Request) -> GitHubIdentity | None:
    raw = request.session.get(_SESSION_IDENTITY_KEY)
    if not isinstance(raw, dict):
        return None
    github_id = raw.get("github_id")
    login = raw.get("login")
    if not isinstance(github_id, int) or isinstance(github_id, bool) or github_id <= 0:
        return None
    if not isinstance(login, str) or not login:
        return None
    name = raw.get("name")
    email = raw.get("email")
    return GitHubIdentity(
        github_id=github_id,
        login=login,
        name=name if isinstance(name, str) else None,
        email=email if isinstance(email, str) else None,
    )


def get_current_user(request: Request) -> GitHubIdentity | None:
    """Return the signed-in user from the validated session, if present."""
    return _identity_from_session(request)


def require_current_user(request: Request) -> GitHubIdentity:
    """Return the signed-in user or raise an HTTP 401 response."""
    identity = get_current_user(request)
    if identity is None:
        raise HTTPException(status_code=401, detail="Sign in with GitHub to continue")
    return identity


def csrf_token_for(request: Request) -> str:
    """Get or create a session-bound token for management form/API mutations."""
    token = request.session.get(_SESSION_CSRF_KEY)
    if not isinstance(token, str) or len(token) < 32:
        token = secrets.token_urlsafe(32)
        request.session[_SESSION_CSRF_KEY] = token
    return token


def verify_csrf_token(request: Request, submitted_token: str | None) -> bool:
    """Check a submitted CSRF token against the current signed session."""
    expected = request.session.get(_SESSION_CSRF_KEY)
    return (
        isinstance(expected, str)
        and isinstance(submitted_token, str)
        and hmac.compare_digest(expected, submitted_token)
    )


def build_management_auth_routes(settings: Settings) -> APIRouter:
    """Create Authlib GitHub login, callback, and logout routes.

    The OAuth callback fetches `/user` over the access token and accepts only
    GitHub's positive numeric account ID as the durable identity key.
    """
    router = APIRouter()
    oauth = OAuth()
    oauth.register(
        name="github",
        client_id=settings.github_client_id,
        client_secret=settings.github_client_secret,
        authorize_url="https://github.com/login/oauth/authorize",
        access_token_url="https://github.com/login/oauth/access_token",
        api_base_url="https://api.github.com/",
        client_kwargs={"scope": "read:user user:email"},
    )

    @router.get("/auth/login", name="github_login")
    async def github_login(request: Request) -> RedirectResponse:
        callback_url = urljoin(settings.public_base_url + "/", "auth/callback")
        return await oauth.github.authorize_redirect(request, callback_url)

    @router.get("/auth/callback", name="github_callback")
    async def github_callback(request: Request) -> RedirectResponse:
        try:
            token = await oauth.github.authorize_access_token(request)
            response = await oauth.github.get("user", token=token)
            response.raise_for_status()
            data = response.json()
            raw_id = data.get("id")
            github_id = int(raw_id)
            login = data.get("login")
            if github_id <= 0 or not isinstance(login, str) or not login:
                raise ValueError("GitHub returned an invalid account identity")
        except (OAuthError, httpx.HTTPError, KeyError, TypeError, ValueError) as exc:
            request.session.clear()
            raise HTTPException(status_code=401, detail="GitHub sign-in could not verify your account") from exc

        identity = GitHubIdentity(
            github_id=github_id,
            login=login,
            name=data.get("name") if isinstance(data.get("name"), str) else None,
            email=data.get("email") if isinstance(data.get("email"), str) else None,
        )
        request.session.clear()
        request.session[_SESSION_IDENTITY_KEY] = identity.as_session_value()
        request.session[_SESSION_CSRF_KEY] = secrets.token_urlsafe(32)
        return RedirectResponse(settings.public_base_url + "/", status_code=303)

    @router.post("/auth/logout", name="github_logout")
    async def github_logout(
        request: Request,
        csrf_token: str | None = Header(default=None, alias="X-CSRF-Token"),
    ) -> RedirectResponse:
        if not verify_csrf_token(request, csrf_token):
            raise HTTPException(status_code=403, detail="Invalid CSRF token")
        request.session.clear()
        return RedirectResponse(settings.public_base_url + "/", status_code=303)

    return router
