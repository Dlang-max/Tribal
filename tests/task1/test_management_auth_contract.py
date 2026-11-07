from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI, HTTPException, Request
from fastapi.testclient import TestClient

from tribal.authentication import (
    GitHubIdentity,
    add_management_session_middleware,
    build_management_auth_routes,
    csrf_token_for,
    get_current_user,
    require_current_user,
    verify_csrf_token,
)
from tribal.settings import Settings


def make_settings() -> Settings:
    return Settings(
        public_base_url="https://tribal.example",
        github_client_id="github-client",
        github_client_secret="github-secret",
        token_signing_key="worker-token-key-with-sufficient-entropy",
        session_signing_key="management-session-key-with-sufficient-entropy",
    )


def make_management_app(settings: Settings) -> FastAPI:
    app = FastAPI()
    add_management_session_middleware(app, settings)
    app.include_router(build_management_auth_routes(settings))

    @app.get("/test/session")
    async def session_state(request: Request):
        user = get_current_user(request)
        return {
            "user": user.as_session_value() if user else None,
            "csrf": csrf_token_for(request),
        }

    @app.post("/test/mutate")
    async def mutate(request: Request):
        submitted = request.headers.get("X-CSRF-Token")
        if not verify_csrf_token(request, submitted):
            raise HTTPException(status_code=403, detail="Invalid CSRF token")
        return {"ok": True}

    @app.get("/test/require-user")
    async def require_user(request: Request):
        return require_current_user(request).as_session_value()

    return app


class FakeGitHubResponse:
    def __init__(self, payload):
        self.payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self.payload


def route_oauth(router, route_path: str):
    route = next(route for route in router.routes if route.path == route_path)
    return dict(zip(route.endpoint.__code__.co_freevars, route.endpoint.__closure__))[
        "oauth"
    ].cell_contents


def test_github_callback_uses_upstream_numeric_id_as_identity(monkeypatch):
    settings = make_settings()
    router = build_management_auth_routes(settings)
    oauth = route_oauth(router, "/auth/callback")
    monkeypatch.setattr(
        oauth.github,
        "authorize_access_token",
        AsyncMock(return_value={"access_token": "fake-github-token"}),
    )
    fake_get = AsyncMock(
        return_value=FakeGitHubResponse(
            {"id": 8675309, "login": "alice", "name": "Alice", "email": "a@example.test"}
        )
    )
    monkeypatch.setattr(oauth.github, "get", fake_get)
    app = FastAPI()
    add_management_session_middleware(app, settings)
    app.include_router(router)
    @app.get("/whoami")
    async def whoami(request: Request):
        return get_current_user(request).as_session_value()

    with TestClient(app, base_url="https://tribal.example") as client:
        response = client.get("/auth/callback?code=fixture&state=fixture", follow_redirects=False)
        assert response.status_code == 303
        assert response.headers["location"] == "https://tribal.example/"
        identity_response = client.get("/whoami")

    assert identity_response.json() == {
        "github_id": 8675309,
        "login": "alice",
        "name": "Alice",
        "email": "a@example.test",
    }
    fake_get.assert_awaited_once_with("user", token={"access_token": "fake-github-token"})


def test_callback_rejects_github_response_without_numeric_identity(monkeypatch):
    settings = make_settings()
    router = build_management_auth_routes(settings)
    oauth = route_oauth(router, "/auth/callback")
    monkeypatch.setattr(oauth.github, "authorize_access_token", AsyncMock(return_value={}))
    monkeypatch.setattr(
        oauth.github,
        "get",
        AsyncMock(return_value=FakeGitHubResponse({"id": 0, "login": "intruder"})),
    )
    app = FastAPI()
    add_management_session_middleware(app, settings)
    app.include_router(router)

    with TestClient(app, base_url="https://tribal.example") as client:
        response = client.get("/auth/callback?code=fixture&state=fixture")

    assert response.status_code == 401


def test_session_cookie_is_signed_http_only_and_secure_for_https():
    settings = make_settings()
    app = make_management_app(settings)

    with TestClient(app, base_url="https://tribal.example") as client:
        response = client.get("/test/session")
        cookie_header = response.headers["set-cookie"]

    assert "tribal_session=" in cookie_header
    assert "httponly" in cookie_header.lower()
    assert "secure" in cookie_header.lower()
    assert "samesite=lax" in cookie_header.lower()


def test_session_signature_tampering_turns_identity_back_into_anonymous():
    settings = make_settings()
    app = make_management_app(settings)
    app_identity_path = "/test/session"

    @app.get("/test/set-identity")
    async def set_identity(request: Request):
        request.session["github_identity"] = GitHubIdentity(8675309, "alice").as_session_value()
        return {"ok": True}

    with TestClient(app, base_url="https://tribal.example") as client:
        client.get("/test/set-identity")
        assert client.get(app_identity_path).json()["user"]["github_id"] == 8675309
        cookie = client.cookies.get("tribal_session")
        payload, signature = cookie.rsplit(".", 1)
        changed_signature = ("a" if signature[0] != "a" else "b") + signature[1:]

    with TestClient(app, base_url="https://tribal.example") as anonymous_client:
        anonymous_client.cookies.set("tribal_session", f"{payload}.{changed_signature}")
        tampered = anonymous_client.get(app_identity_path)

    assert tampered.json()["user"] is None


def test_csrf_token_must_match_the_session():
    app = make_management_app(make_settings())

    with TestClient(app, base_url="https://tribal.example") as client:
        token = client.get("/test/session").json()["csrf"]
        accepted = client.post("/test/mutate", headers={"X-CSRF-Token": token})
        rejected = client.post("/test/mutate", headers={"X-CSRF-Token": "attacker-value"})
        missing = client.post("/test/mutate")

    assert accepted.status_code == 200
    assert rejected.status_code == 403
    assert missing.status_code == 403


def test_require_current_user_rejects_anonymous_requests():
    app = make_management_app(make_settings())

    with TestClient(app, base_url="https://tribal.example") as client:
        response = client.get("/test/require-user")

    assert response.status_code == 401
