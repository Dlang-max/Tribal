"""Serve Tribal public MCP, scoped curator tools, and live graph activity."""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
import json
from pathlib import Path

from typing import Literal, Protocol, TypedDict

from fastmcp import FastMCP
from fastmcp.exceptions import ToolError


class Source(TypedDict):
    path: str
    title: str


class ContextResult(TypedDict):
    context: str
    sources: list[Source]


class NoteChange(TypedDict):
    path: str
    action: Literal["created", "updated", "archived"]


class UpdateResult(TypedDict):
    status: Literal["updated", "unchanged", "needs_information"]
    message: str
    notes: list[NoteChange]


class Curator(Protocol):
    """Define the boundary implemented by each configured curator runtime."""

    # Retrieve context through a curation run.
    async def seed_agent_context(
        self, task: str, repository: str | None, branch: str | None
    ) -> ContextResult: ...

    # Review and apply an update through a curation run.
    async def update_knowledge_base(
        self, request_id: str, content: str, repository: str | None, branch: str | None
    ) -> UpdateResult: ...


# Reject missing or whitespace-only arguments without altering their values.
def require_text(name: str, value: str | None) -> None:
    if value is not None and not value.strip():
        raise ToolError(f"{name} must not be blank")


# Enforce the shared repository and branch scope rules.
def validate_scope(repository: str | None, branch: str | None) -> None:
    require_text("repository", repository)
    require_text("branch", branch)
    if branch is not None and repository is None:
        raise ToolError("branch requires repository")


# Build an unauthenticated MCP server that delegates requests to a curator.
def create_server(curator: Curator | None = None) -> FastMCP:
    server = FastMCP("Tribal knowledge base")

    # Retrieve relevant context from the curation agent.
    @server.tool()
    async def seed_agent_context(
        task: str, repository: str | None = None, branch: str | None = None
    ) -> ContextResult:
        """Retrieve project context relevant to a task and its optional scope."""
        require_text("task", task)
        validate_scope(repository, branch)
        if curator is None:
            raise ToolError("Knowledge curation agent is not connected")
        return await curator.seed_agent_context(task, repository, branch)

    # Submit information to the curation agent for review and publication.
    @server.tool()
    async def update_knowledge_base(
        request_id: str, content: str, repository: str | None = None, branch: str | None = None
    ) -> UpdateResult:
        """Request a knowledge-base update using a unique replay ID and evidence."""
        require_text("request_id", request_id)
        require_text("content", content)
        validate_scope(repository, branch)
        if curator is None:
            raise ToolError("Knowledge curation agent is not connected")
        return await curator.update_knowledge_base(request_id, content, repository, branch)

    return server


class PrivateRunTokenMiddleware:
    """Reject HTTP requests lacking an active private curator token."""

    # Bind the private transport to its owning runtime token registry.
    def __init__(self, app, curator) -> None:
        self.app = app
        self.curator = curator

    # Check tokens on every private HTTP request, including MCP initialization.
    async def __call__(self, scope, receive, send) -> None:
        if scope["type"] == "http":
            headers = dict(scope.get("headers", []))
            token = headers.get(b"x-tribal-run-token", b"").decode("ascii", errors="ignore")
            if token not in self.curator.runs:
                from starlette.responses import JSONResponse

                await JSONResponse({"error": "Missing or expired curator run token"}, status_code=403)(
                    scope, receive, send,
                )
                return
        await self.app(scope, receive, send)


# Compose the local MCP endpoints and browser APIs with injectable real service boundaries.
def create_app(service=None, curator=None, events=None, settings=None):
    from fastapi import FastAPI, HTTPException
    from fastapi.responses import FileResponse, StreamingResponse
    from fastapi.staticfiles import StaticFiles
    from tribal_kb.activity import ActivityBus
    from tribal_kb.authentication import MCPBearerTokenMiddleware
    from tribal_kb.runtime import CodexCurator

    events = events if events is not None else getattr(curator, "events", None) or ActivityBus()
    if service is None and curator is not None:
        service = getattr(curator, "service", None)
    if service is None:
        from tribal_kb.configuration import Settings, build_service

        settings = settings or Settings.from_env()
        service = build_service(settings)
    if curator is None:
        from tribal_kb.configuration import Settings

        settings = settings or Settings.from_env()
        curator = CodexCurator(
            service, events, codex_bin=settings.codex_bin, internal_url=settings.internal_url,
            timeout_seconds=settings.curator_timeout_seconds, model=settings.codex_model,
        )
    public_app = create_server(curator).http_app(path="/mcp", stateless_http=True)
    private_server = getattr(curator, "internal_server", None)
    private_app = private_server.http_app(path="/mcp", stateless_http=True) if private_server else None

    # Enter both MCP session managers and drain background indexing on shutdown.
    @asynccontextmanager
    async def lifespan(app):
        async with public_app.lifespan(app):
            if private_app is None:
                yield
            else:
                async with private_app.lifespan(app):
                    try:
                        yield
                    finally:
                        if hasattr(curator, "close"):
                            await curator.close()
                        if hasattr(service, "drain_indexing"):
                            await service.drain_indexing()

    app = FastAPI(title="Tribal local project server", lifespan=lifespan)
    app.state.curator = curator
    app.state.service = service
    app.state.events = events

    # Report process health without claiming storage or Codex authentication success.
    @app.get("/healthz")
    async def health():
        return {"status": "ok", "project_id": getattr(service, "project_id", None)}

    # Return the authoritative current note and verified-link snapshot.
    @app.get("/api/graph")
    async def graph():
        return await service.graph()

    # Read a published note by stable ID for the graph viewer's file reader.
    @app.get("/api/notes/{note_id:path}")
    async def note_contents(note_id: str):
        try:
            return await service.read_note(note_id)
        except KeyError as error:
            raise HTTPException(status_code=404, detail="Note not found") from error

    # Broadcast default SSE message events with periodic keepalive comments.
    @app.get("/api/activity")
    async def activity():
        # Remove the subscriber promptly when its response is cancelled or disconnected.
        async def stream():
            async with events.subscribe() as queue:
                yield ": connected\n\n"
                while True:
                    try:
                        event = await asyncio.wait_for(queue.get(), timeout=15)
                    except asyncio.TimeoutError:
                        yield ": heartbeat\n\n"
                    else:
                        yield "data: " + json.dumps(event) + "\n\n"

        return StreamingResponse(stream(), media_type="text/event-stream", headers={
            "Cache-Control": "no-cache", "X-Accel-Buffering": "no",
        })

    if private_app is not None:
        app.mount("/internal", PrivateRunTokenMiddleware(private_app, curator))
    gui_directory = getattr(settings, "gui_directory", None)
    if gui_directory:
        gui = Path(gui_directory).resolve()
        if not (gui / "index.html").is_file():
            raise ValueError(f"GUI directory has no index.html: {gui}")
        if (gui / "assets").is_dir():
            app.mount("/assets", StaticFiles(directory=gui / "assets"), name="gui-assets")

        # Serve the optional built dashboard from the same origin as its live APIs.
        @app.get("/")
        async def dashboard():
            return FileResponse(gui / "index.html")

    app.mount("/", MCPBearerTokenMiddleware(
        public_app, getattr(settings, "mcp_bearer_token", None),
    ))
    return app


# Load production configuration and start the trusted local ASGI server.
def main() -> None:
    import uvicorn
    from tribal_kb.configuration import Settings

    settings = Settings.from_env()
    uvicorn.run(create_app(settings=settings), host=settings.host, port=settings.port)


if __name__ == "__main__":
    main()
