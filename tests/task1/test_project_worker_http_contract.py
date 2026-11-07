from unittest.mock import AsyncMock
import asyncio
import time
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from fastmcp.server.auth import AccessToken
from fastmcp.server.auth.providers.github import GitHubProvider
from fastmcp.server.auth.providers.github import GitHubTokenVerifier
from fastmcp.server.auth.oauth_proxy.models import JTIMapping, UpstreamTokenSet

from tribal.project_worker import build_project_worker
from tribal.settings import Settings


PROJECT_ID = "45c62769-57ed-479d-9b95-fbb75e0dba95"
ROOT = "https://tribal.example"


def worker_settings(allowed_ids=frozenset({42})) -> Settings:
    return Settings(
        public_base_url=ROOT,
        github_client_id="github-client",
        github_client_secret="github-secret",
        token_signing_key="worker-token-key-with-sufficient-entropy",
        session_signing_key="management-session-key-with-sufficient-entropy",
        project_id=PROJECT_ID,
        project_name="Example",
        allowed_github_ids=allowed_ids,
    )


@pytest.fixture
def fake_github_verifier(monkeypatch):
    async def verify(token: str):
        try:
            github_id = int(token.removeprefix("fixture-user-"))
        except ValueError:
            return None
        return AccessToken(
            token=token,
            client_id="fixture-client",
            scopes=["user"],
            subject=str(github_id),
            claims={"sub": str(github_id)},
        )

    verifier = AsyncMock(side_effect=verify)
    monkeypatch.setattr(GitHubProvider, "verify_token", verifier)
    return verifier


def mcp_post(client: TestClient, method: str, token: str, *, request_id=1):
    return client.post(
        f"/projects/{PROJECT_ID}/mcp",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "jsonrpc": "2.0",
            "id": request_id,
            "method": method,
            "params": (
                {
                    "protocolVersion": "2025-03-26",
                    "capabilities": {},
                    "clientInfo": {"name": "contract-test", "version": "1"},
                }
                if method == "initialize"
                else {"name": "get_project_context", "arguments": {}}
            ),
        },
    )


def test_worker_publishes_project_specific_oauth_resource_and_issuer(fake_github_verifier):
    app = build_project_worker(worker_settings())
    with TestClient(app) as client:
        authorization = client.get(
            f"/.well-known/oauth-authorization-server/projects/{PROJECT_ID}"
        )
        protected_resource = client.get(
            f"/.well-known/oauth-protected-resource/projects/{PROJECT_ID}/mcp"
        )

    assert authorization.status_code == 200
    assert authorization.json()["issuer"] == f"{ROOT}/projects/{PROJECT_ID}"
    assert authorization.json()["authorization_endpoint"] == f"{ROOT}/projects/{PROJECT_ID}/authorize"
    assert protected_resource.status_code == 200
    assert protected_resource.json()["resource"] == f"{ROOT}/projects/{PROJECT_ID}/mcp"
    assert protected_resource.json()["authorization_servers"] == [
        f"{ROOT}/projects/{PROJECT_ID}"
    ]


def test_worker_returns_stateless_json_mcp_and_binds_context_to_configured_project(
    fake_github_verifier,
):
    app = build_project_worker(worker_settings())
    with TestClient(app) as client:
        initialized = mcp_post(client, "initialize", "fixture-user-42")
        context_response = mcp_post(client, "tools/call", "fixture-user-42", request_id=2)
        repeated_context_response = mcp_post(
            client, "tools/call", "fixture-user-42", request_id=3
        )

    assert initialized.status_code == 200
    assert initialized.headers["content-type"].startswith("application/json")
    assert "mcp-session-id" not in initialized.headers
    result = context_response.json()["result"]["structuredContent"]
    assert result == {
        "id": PROJECT_ID,
        "name": "Example",
        "sample": True,
        "context": "Sample context for Example.",
    }
    assert repeated_context_response.json()["result"]["structuredContent"] == result
    assert fake_github_verifier.await_count == 3


def test_worker_health_and_readiness_are_available_without_oauth():
    app = build_project_worker(worker_settings())
    with TestClient(app) as client:
        health = client.get("/healthz")
        readiness = client.get("/readyz")

    assert health.status_code == 200
    assert health.json() == {"status": "ok"}
    assert readiness.status_code == 200
    assert readiness.json() == {"status": "ready"}


def test_worker_denies_nonmember_tool_call_without_returning_project_context(fake_github_verifier):
    app = build_project_worker(worker_settings(allowed_ids=frozenset({42})))
    with TestClient(app) as client:
        denied = mcp_post(client, "tools/call", "fixture-user-867")

    assert denied.status_code == 200
    payload = denied.json()["result"]
    assert payload["isError"] is True
    assert "not allowed" in payload["content"][0]["text"].lower()
    assert PROJECT_ID not in denied.text
    fake_github_verifier.assert_awaited_once()


def test_project_a_token_is_accepted_by_a_and_rejected_by_b(monkeypatch):
    async def fake_github_upstream_verification(token: str):
        github_id = token.removeprefix("fake-github-user-")
        return AccessToken(
            token=token,
            client_id=github_id,
            scopes=["user"],
            subject=github_id,
            claims={"sub": github_id},
        )

    upstream_verifier = AsyncMock(side_effect=fake_github_upstream_verification)
    monkeypatch.setattr(GitHubTokenVerifier, "verify_token", upstream_verifier)

    project_a_id = PROJECT_ID
    project_b_id = "fc0b6d32-9ed4-4e4a-b54a-7ad2c60451fe"
    project_a = worker_settings(allowed_ids=frozenset({42}))
    project_b = Settings(
        public_base_url=ROOT,
        github_client_id="github-client",
        github_client_secret="github-secret",
        token_signing_key="a-different-project-b-signing-key",
        session_signing_key="management-session-signing-key",
        project_id=project_b_id,
        project_name="Beta",
        allowed_github_ids=frozenset({42}),
    )
    app_a = build_project_worker(project_a)
    app_b = build_project_worker(project_b)

    async def issue_project_a_token() -> str:
        provider_a = app_a.router.routes[-1].app.state.fastmcp_auth
        jti = uuid4().hex
        upstream_token_id = uuid4().hex
        now = time.time()
        await provider_a._jti_mapping_store.put(
            key=jti,
            value=JTIMapping(
                jti=jti,
                upstream_token_id=upstream_token_id,
                created_at=now,
            ),
            ttl=3600,
        )
        await provider_a._upstream_token_store.put(
            key=upstream_token_id,
            value=UpstreamTokenSet(
                upstream_token_id=upstream_token_id,
                access_token="fake-github-user-42",
                refresh_token=None,
                refresh_token_expires_at=None,
                expires_at=now + 3600,
                token_type="Bearer",
                scope="user",
                client_id="fixture-client",
                created_at=now,
            ),
            ttl=3600,
        )
        return provider_a.jwt_issuer.issue_access_token(
            client_id="fixture-client",
            scopes=["user"],
            jti=jti,
            expires_in=3600,
        )

    token_a = asyncio.run(issue_project_a_token())
    provider_a = app_a.router.routes[-1].app.state.fastmcp_auth
    provider_b = app_b.router.routes[-1].app.state.fastmcp_auth
    assert provider_a.jwt_issuer.issuer == f"{ROOT}/projects/{project_a_id}"
    assert provider_a.jwt_issuer.audience == f"{ROOT}/projects/{project_a_id}/mcp"
    assert provider_b.jwt_issuer.issuer == f"{ROOT}/projects/{project_b_id}"
    assert provider_b.jwt_issuer.audience == f"{ROOT}/projects/{project_b_id}/mcp"

    with TestClient(app_a) as client_a, TestClient(app_b) as client_b:
        accepted_by_a = mcp_post(client_a, "tools/call", token_a)
        rejected_by_b = client_b.post(
            f"/projects/{project_b_id}/mcp",
            headers={"Authorization": f"Bearer {token_a}"},
            json={
                "jsonrpc": "2.0",
                "id": 1,
                "method": "tools/call",
                "params": {"name": "get_project_context", "arguments": {}},
            },
        )

    assert accepted_by_a.status_code == 200
    assert accepted_by_a.json()["result"]["structuredContent"]["id"] == project_a_id
    assert rejected_by_b.status_code == 401
    assert "resource_metadata=" in rejected_by_b.headers["www-authenticate"]
    assert project_a_id not in rejected_by_b.text
    assert project_b_id not in rejected_by_b.text
    upstream_verifier.assert_awaited_once_with("fake-github-user-42")


def test_worker_mcp_route_requires_bearer_authentication():
    app = build_project_worker(worker_settings())
    with TestClient(app) as client:
        response = client.post(
            f"/projects/{PROJECT_ID}/mcp",
            json={
                "jsonrpc": "2.0",
                "id": 1,
                "method": "tools/call",
                "params": {"name": "get_project_context", "arguments": {}},
            },
        )

    assert response.status_code == 401
    assert "resource_metadata=" in response.headers["www-authenticate"]
