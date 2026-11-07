"""Stateless project-scoped MCP worker protected by GitHub OAuth."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from contextlib import asynccontextmanager
from collections.abc import AsyncIterator

from fastapi import FastAPI
from fastmcp import FastMCP
from fastmcp.exceptions import ToolError
from fastmcp.server.auth.providers.github import GitHubProvider
from fastmcp.server.dependencies import get_access_token
from fastmcp.server.middleware import Middleware, MiddlewareContext
from starlette.applications import Starlette

from tribal.settings import Settings


class ProjectAccessMiddleware(Middleware):
    """Reject every tool call whose verified GitHub ID is outside the project list."""

    def __init__(self, allowed_github_ids: frozenset[int]) -> None:
        self.allowed_github_ids = allowed_github_ids

    async def on_call_tool(self, context: MiddlewareContext[Any], call_next: Any) -> Any:
        access_token = get_access_token()
        raw_id = access_token.claims.get("sub") if access_token is not None else None
        try:
            github_id = int(raw_id)
        except (TypeError, ValueError):
            raise ToolError("GitHub identity is unavailable")
        if github_id not in self.allowed_github_ids:
            raise ToolError("This GitHub account is not allowed for this project")
        return await call_next(context)


def create_project_context(settings: Settings) -> dict[str, Any]:
    """Build the explicitly labeled sample payload for a project."""
    settings.require_worker_config()
    return {
        "id": settings.project_id,
        "name": settings.project_name,
        "sample": True,
        "context": f"Sample context for {settings.project_name}.",
    }


def build_project_worker(settings: Settings) -> Starlette:
    """Build the per-project worker ASGI app, including MCP auth and health routes."""
    settings.require_worker_config()
    try:
        project_id = str(UUID(settings.project_id or ""))
    except ValueError as exc:
        raise ValueError("PROJECT_ID must be a UUID") from exc

    project_url = f"{settings.public_base_url}/projects/{project_id}"
    auth = GitHubProvider(
        client_id=settings.github_client_id,
        client_secret=settings.github_client_secret,
        base_url=project_url,
        resource_base_url=project_url,
        issuer_url=project_url,
        jwt_signing_key=settings.token_signing_key,
        required_scopes=["user"],
        require_authorization_consent=True,
    )
    mcp = FastMCP(
        f"Tribal: {settings.project_name}",
        auth=auth,
        middleware=[ProjectAccessMiddleware(settings.allowed_github_ids)],
    )

    @mcp.tool()
    async def get_project_context() -> dict[str, Any]:
        """Return this project's explicitly labeled sample context."""
        return create_project_context(settings)

    mcp_http = mcp.http_app(
        path="/mcp",
        stateless_http=True,
        json_response=True,
    )

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        async with mcp_http.router.lifespan_context(mcp_http):
            yield

    api = FastAPI(
        title="Tribal project worker",
        docs_url=None,
        redoc_url=None,
        lifespan=lifespan,
    )

    @api.get("/healthz", include_in_schema=False)
    async def healthz() -> dict[str, str]:
        return {"status": "ok"}

    @api.get("/readyz", include_in_schema=False)
    async def readyz() -> dict[str, str]:
        return {"status": "ready"}

    # OAuth discovery uses RFC 8414/9728 root-level paths. FastMCP derives the
    # project-specific metadata routes from this provider; forward those routes
    # at the host root while also mounting all operational OAuth/MCP endpoints
    # under the public project prefix expected by the Traefik Ingress.
    api.router.routes.extend(auth.get_well_known_routes("/mcp"))
    api.mount(f"/projects/{project_id}", mcp_http)
    return api
