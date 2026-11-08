"""Expose Tribal's two MCP tools and a boundary for a future curation agent."""

from __future__ import annotations

import os
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
    """Define the boundary that the future knowledge-curation agent implements."""

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


# Start a local HTTP MCP endpoint for clients such as Codex.
def main() -> None:
    create_server().run(
        transport="http", host=os.environ.get("HOST", "127.0.0.1"), port=8000, path="/mcp"
    )


if __name__ == "__main__":
    main()
