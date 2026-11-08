"""Exercise the public MCP contract and runtime HTTP assembly without model calls."""

import asyncio
import importlib

from fastmcp import Client
import pytest

server = importlib.import_module("server")


# Detect missing runtime assembly before dependencies can hide the contract failure.
def test_runtime_exposes_http_app_factory():
    assert callable(getattr(server, "create_app", None)), (
        "Runtime must expose create_app for public/private MCP, graph, activity and health routes"
    )


# Verify retrieval and mutation remain the only tools visible to callers.
def test_public_mcp_has_exactly_two_scoped_tools():
    # Read tools through the MCP client rather than framework registration internals.
    async def exercise():
        async with Client(server.create_server()) as client:
            tools = {tool.name: tool.input_schema for tool in await client.list_tools()}
        assert set(tools) == {"seed_agent_context", "update_knowledge_base"}
        assert tools["seed_agent_context"]["required"] == ["task"]
        assert tools["update_knowledge_base"]["required"] == ["request_id", "content"]
        assert set(tools["seed_agent_context"]["properties"]) == {"task", "repository", "branch"}
        assert set(tools["update_knowledge_base"]["properties"]) == {
            "request_id", "content", "repository", "branch"
        }
    asyncio.run(exercise())


# Reject malformed scope and blank content before starting any curator work.
@pytest.mark.parametrize("tool,arguments", [
    ("seed_agent_context", {"task": "  "}),
    ("seed_agent_context", {"task": "read", "branch": "main"}),
    ("seed_agent_context", {"task": "read", "repository": "  "}),
    ("update_knowledge_base", {"request_id": " ", "content": "evidence"}),
    ("update_knowledge_base", {"request_id": "r1", "content": "\n"}),
    ("update_knowledge_base", {"request_id": "r1", "content": "evidence", "branch": "main"}),
])
def test_public_mcp_rejects_invalid_arguments(tool, arguments):
    # Call the real protocol with error raising disabled so structured failures are observable.
    async def exercise():
        async with Client(server.create_server()) as client:
            result = await client.call_tool(tool, arguments, raise_on_error=False)
        assert result.is_error
        assert "not connected" not in str(result.content).lower()
    asyncio.run(exercise())
