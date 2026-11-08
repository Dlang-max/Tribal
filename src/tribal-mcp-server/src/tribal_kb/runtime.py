"""Run isolated concurrent Codex curators with scoped tools and checked receipts."""

from __future__ import annotations

import asyncio
from contextlib import suppress
from dataclasses import dataclass, field
import hashlib
import json
import os
from pathlib import Path
import secrets
import signal
import tempfile
from typing import Any
from uuid import uuid4

from fastmcp import FastMCP
from fastmcp.exceptions import ToolError
from fastmcp.server.dependencies import get_http_headers
from fastmcp.server.middleware import Middleware
import jsonschema

from .activity import ActivityBus

RESOURCES = Path(__file__).parent / "resources"
READ_TOOLS = ["search_notes", "read_note", "follow_link", "get_note_spec"]
COLORS = ["#059669", "#2563eb", "#9333ea", "#d97706", "#db2777", "#0891b2"]


@dataclass
class RunState:
    run_id: str
    name: str
    color: str
    writable: bool
    request_id: str | None = None
    request_hash: str | None = None
    reads: dict[str, dict] = field(default_factory=dict)
    receipt: dict | None = None
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    tool_tasks: set[asyncio.Task] = field(default_factory=set)
    active: bool = True


class RunPermissions(Middleware):
    # Bind middleware to the runtime's live token registry.
    def __init__(self, curator: CodexCurator) -> None:
        self.curator = curator

    # Hide the write tool from context-only curator sessions.
    async def on_list_tools(self, context, call_next):
        run = self.curator.current_run()
        tools = await call_next(context)
        return tools if run.writable else [tool for tool in tools if tool.name != "apply_changes"]

    # Recheck token validity and write scope for every execution.
    async def on_call_tool(self, context, call_next):
        run = self.curator.current_run()
        if context.message.name == "apply_changes" and not run.writable:
            raise ToolError("This curator run is read-only")
        task = asyncio.current_task()
        run.tool_tasks.add(task)
        self.curator._tool_tasks.add(task)
        try:
            return await call_next(context)
        finally:
            run.tool_tasks.discard(task)
            self.curator._tool_tasks.discard(task)


class CodexCurator:
    """Expose the public Curator protocol through real ephemeral Codex processes."""

    # Configure a runtime without starting a process or touching the knowledge base.
    def __init__(
        self, service, events: ActivityBus, *, codex_bin: str = "codex",
        internal_url: str, timeout_seconds: float = 300, model: str | None = None,
        process_runner=None,
    ) -> None:
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")
        self.service = service
        self.events = events
        self.codex_bin = codex_bin
        self.internal_url = internal_url
        self.timeout_seconds = timeout_seconds
        self.model = model
        self.process_runner = process_runner or asyncio.create_subprocess_exec
        self.runs: dict[str, RunState] = {}
        self._request_locks: dict[str, asyncio.Lock] = {}
        self._request_users: dict[str, int] = {}
        self._active_tasks: set[asyncio.Task] = set()
        self._tool_tasks: set[asyncio.Task] = set()
        self.internal_server = self._create_internal_server()

    # Cancel and reap active runs before the HTTP endpoint stops accepting tools.
    async def close(self) -> None:
        tasks = tuple(self._active_tasks)
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        await self._cancel_tool_tasks(self._tool_tasks)

    # Revoke transport and tool permissions without waiting for storage or tool locks.
    def _revoke_run(self, token: str, run: RunState) -> None:
        run.active = False
        self.runs.pop(token, None)

    # Cancel private executions without indefinitely waiting for cancellation-resistant I/O.
    async def _cancel_tool_tasks(self, tasks: set[asyncio.Task]) -> bool:
        pending = {task for task in tasks if not task.done()}
        for task in pending:
            task.cancel()
        if pending:
            done, _ = await asyncio.wait(pending, timeout=0.25)
            for task in done:
                if not task.cancelled():
                    task.exception()
        return bool(pending)

    # Resolve only a currently active per-run HTTP token.
    def current_run(self) -> RunState:
        token = get_http_headers().get("x-tribal-run-token", "")
        run = self.runs.get(token)
        if run is None:
            raise ToolError("Missing or expired curator run token")
        return run

    # Publish a consistent activity envelope without private model reasoning.
    async def emit(self, run: RunState, kind: str, message: str, *,
                   status: str = "working", node_ids=None, edge_ids=None) -> None:
        if not run.active and kind in {"activity", "graph_changed"}:
            return
        await self.events.publish({
            "type": kind, "run_id": run.run_id, "name": run.name, "color": run.color,
            "message": message, "status": status,
            "node_ids": node_ids or [], "edge_ids": edge_ids or [],
        })

    # Expose exactly the five internal operations through scope-checked wrappers.
    def _create_internal_server(self) -> FastMCP:
        server = FastMCP("Tribal private curator tools")
        server.add_middleware(RunPermissions(self))

        # Search project notes and report only observed search candidates.
        @server.tool()
        async def search_notes(query: str, limit: int = 10) -> list[dict]:
            run = self.current_run()
            async with run.lock:
                self.current_run()
                result = await self.service.search_notes(query, limit)
                await self.emit(run, "activity", f"Searched notes: {query[:160]}",
                                node_ids=[note["id"] for note in result])
                return result

        # Record the actual note used as a public context source.
        @server.tool()
        async def read_note(note_id: str) -> dict:
            run = self.current_run()
            async with run.lock:
                self.current_run()
                note = await self.service.read_note(note_id)
                run.reads[note["path"]] = note
                await self.emit(run, "activity", f"Read {note['title']}", node_ids=[note["id"]])
                return note

        # Traverse a verified stored edge and record its target as read evidence.
        @server.tool()
        async def follow_link(source_id: str, target_id: str) -> dict:
            run = self.current_run()
            async with run.lock:
                self.current_run()
                note = await self.service.follow_link(source_id, target_id)
                run.reads[note["path"]] = note
                graph = await self.service.graph()
                edge_ids = [edge["id"] for edge in graph["edges"]
                            if edge["source"] == source_id and edge["target"] == target_id]
                await self.emit(run, "activity", f"Followed link to {note['title']}",
                                node_ids=[source_id, target_id], edge_ids=edge_ids)
                return note

        # Retrieve the trusted publication rules for an allowed note type.
        @server.tool()
        async def get_note_spec(note_type: str) -> str:
            run = self.current_run()
            async with run.lock:
                self.current_run()
                result = await self.service.get_note_spec(note_type)
                await self.emit(run, "activity", f"Read {note_type} note specification")
                return result

        # Publish one validated batch and retain its authoritative save receipt.
        @server.tool()
        async def apply_changes(changes: list[dict]) -> dict:
            run = self.current_run()
            async with run.lock:
                self.current_run()
                if not run.writable:
                    raise ToolError("This curator run is read-only")
                if run.receipt is not None:
                    raise ToolError("This request already published; return its saved receipt")
                result = await self.service.apply_changes(
                    changes, request_id=run.request_id, request_hash=run.request_hash,
                )
                if result["status"] == "updated":
                    run.receipt = {key: result[key] for key in ("status", "message", "notes")}
                    graph = await self.service.graph()
                    paths = {note["path"] for note in result["notes"]}
                    await self.emit(run, "graph_changed", result["message"],
                                    node_ids=[node["id"] for node in graph["nodes"]
                                              if node["path"] in paths])
                else:
                    await self.emit(run, "activity", f"Publication {result['status']}")
                return result

        return server

    # Retrieve task context through one independent read-only curator process.
    async def seed_agent_context(self, task: str, repository: str | None = None,
                                 branch: str | None = None) -> dict:
        return await self._run("context", {"task": task, "repository": repository, "branch": branch})

    # Reuse completed requests and serialize only identical replay IDs.
    async def update_knowledge_base(self, request_id: str, content: str,
                                    repository: str | None = None,
                                    branch: str | None = None) -> dict:
        payload = {"content": content, "repository": repository, "branch": branch}
        request_hash = hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()
        lock = self._request_locks.setdefault(request_id, asyncio.Lock())
        self._request_users[request_id] = self._request_users.get(request_id, 0) + 1
        try:
            async with lock:
                previous = await self.service.get_request_result(request_id, request_hash)
                if previous is not None:
                    return {key: previous[key] for key in ("status", "message", "notes")}
                result = await self._run("update", payload, request_id, request_hash)
                await self.service.remember_request_result(request_id, request_hash, result)
                return result
        finally:
            self._request_users[request_id] -= 1
            if not self._request_users[request_id]:
                self._request_users.pop(request_id)
                self._request_locks.pop(request_id)

    # Launch a scoped process, verify its result, and revoke permissions on every exit.
    async def _run(self, kind: str, payload: dict, request_id: str | None = None,
                   request_hash: str | None = None) -> dict:
        task = asyncio.current_task()
        self._active_tasks.add(task)
        run_id = str(uuid4())
        active_colors = {active.color for active in self.runs.values()}
        palette = [color for color in COLORS if color not in active_colors] or COLORS
        run = RunState(run_id, f"Curator {run_id[:6]}", secrets.choice(palette),
                       kind == "update", request_id, request_hash)
        token = secrets.token_urlsafe(32)
        self.runs[token] = run
        try:
            await self.emit(run, "run_started", "Reviewing knowledge update" if run.writable
                            else "Gathering task context")
            with tempfile.TemporaryDirectory(prefix="tribal-curator-") as workspace:
                result = await self._execute(run, token, kind, payload, Path(workspace))
                self._revoke_run(token, run)
                if await self._cancel_tool_tasks(run.tool_tasks):
                    # A blocking write may still commit; retry reconciles its durable receipt.
                    raise RuntimeError("Curator exited with unfinished knowledge operations; retry the same request ID")
                self._check_receipts(run, result)
                await self.emit(run, "run_finished", "Knowledge update complete" if run.writable
                                else "Context ready", status="done")
                return result
        except BaseException as error:
            self._revoke_run(token, run)
            await self._cancel_tool_tasks(run.tool_tasks)
            await self.emit(run, "run_failed", "Curator cancelled" if isinstance(error, asyncio.CancelledError)
                            else f"Curator failed: {type(error).__name__}", status="failed")
            if isinstance(error, asyncio.CancelledError):
                raise
            raise ToolError(f"Curator failed: {error}") from error
        finally:
            self._revoke_run(token, run)
            self._active_tasks.discard(task)

    # Accept context citations and update claims only when real tool receipts support them.
    def _check_receipts(self, run: RunState, result: dict) -> None:
        if not run.writable:
            for source in result["sources"]:
                note = run.reads.get(source["path"])
                if note is None or source["title"] != note["title"]:
                    raise ValueError("Context source was not read by this curator")
        elif run.receipt is not None:
            if result["status"] != "updated" or result["notes"] != run.receipt["notes"]:
                raise ValueError("Final update does not match the actual saved receipt")
            # Prefer the storage-generated message and receipt over model embellishment.
            result.update(run.receipt)
        elif result["status"] == "updated" or result["notes"]:
            raise ValueError("Updated outcome requires an actual saved publication receipt")

    # Pass only process basics and dedicated Codex authentication to the child.
    def _child_environment(self) -> dict[str, str]:
        names = {"PATH", "HOME", "USER", "LOGNAME", "LANG", "LC_ALL", "TMPDIR", "CODEX_HOME",
                 "CODEX_API_KEY", "SSL_CERT_FILE", "SSL_CERT_DIR", "HTTPS_PROXY", "HTTP_PROXY",
                 "ALL_PROXY", "NO_PROXY", "XDG_CONFIG_HOME", "XDG_DATA_HOME"}
        return {key: value for key, value in os.environ.items() if key in names}

    # Execute JSONL Codex with bounded output and a schema-validated final file.
    async def _execute(self, run: RunState, token: str, kind: str, payload: dict,
                       workspace: Path) -> dict:
        schema_path = RESOURCES / f"{kind}-result.schema.json"
        output_path = workspace / "final-result.json"
        tools = READ_TOOLS + (["apply_changes"] if run.writable else [])
        args = [self.codex_bin, "exec", "--json", "--ephemeral", "--ignore-user-config",
                "--skip-git-repo-check", "--ignore-rules", "--sandbox", "read-only", "--color", "never",
                "--output-schema", str(schema_path), "--output-last-message", str(output_path),
                "--cd", str(workspace), "-c", "mcp_servers.tribal.url=" + json.dumps(self.internal_url),
                "-c", 'mcp_servers.tribal.http_headers={"x-tribal-run-token"=' + json.dumps(token) + "}",
                "-c", "mcp_servers.tribal.enabled_tools=" + json.dumps(tools),
                "-c", "mcp_servers.tribal.required=true",
                "-c", 'shell_environment_policy.inherit="none"',
                "-c", 'approval_policy="never"',
                "-c", "features.shell_tool=false", "-c", 'web_search="disabled"',
                "-c", "features.view_image=false"]
        if self.model:
            args += ["--model", self.model]
        args.append("-")
        instructions = (RESOURCES / "curator-instructions.md").read_text()
        prompt = instructions + "\n\nREQUEST KIND: " + kind + "\nUNTRUSTED REQUEST DATA:\n" + json.dumps(payload)
        process = await self.process_runner(
            *args, stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE, cwd=workspace, env=self._child_environment(),
            start_new_session=True,
        )
        try:
            async with asyncio.timeout(self.timeout_seconds):
                stdout_task = asyncio.create_task(self._bounded_read(process.stdout))
                stderr_task = asyncio.create_task(self._bounded_read(process.stderr))
                try:
                    process.stdin.write(prompt.encode())
                    await process.stdin.drain()
                    process.stdin.close()
                    stdout, stderr = await asyncio.gather(stdout_task, stderr_task)
                    await process.wait()
                finally:
                    for task in (stdout_task, stderr_task):
                        if not task.done():
                            task.cancel()
                    await asyncio.gather(stdout_task, stderr_task, return_exceptions=True)
                if process.returncode:
                    # Raw CLI output can include request evidence or credentials; keep errors terse.
                    raise RuntimeError(f"codex exited with status {process.returncode}; check server Codex login/configuration")
                if output_path.exists():
                    if output_path.stat().st_size > 2_000_000:
                        raise ValueError("Codex final output exceeds 2 MB")
                    raw = output_path.read_text()
                else:
                    raw = self._final_jsonl_message(stdout)
                result = json.loads(raw)
                jsonschema.validate(result, json.loads(schema_path.read_text()))
                return result
        finally:
            self._revoke_run(token, run)
            await self._stop_process(process)

    # Drain process pipes without retaining unlimited output or exposing reasoning.
    async def _bounded_read(self, stream) -> bytes:
        result = bytearray()
        while chunk := await stream.read(65536):
            result.extend(chunk)
            if len(result) > 8_000_000:
                raise ValueError("Codex output exceeds 8 MB")
        return bytes(result)

    # Recover a structured final agent message when the CLI omitted its output file.
    def _final_jsonl_message(self, stdout: bytes) -> str:
        final = None
        for line in stdout.decode().splitlines():
            event = json.loads(line)
            item = event.get("item", {})
            if event.get("type") == "item.completed" and item.get("type") == "agent_message":
                final = item.get("text")
        if not isinstance(final, str):
            raise ValueError("Codex returned no final structured result")
        return final

    # Signal the owned group even after its leader exits, and separately reap the leader.
    async def _stop_process(self, process) -> None:
        try:
            with suppress(ProcessLookupError):
                os.killpg(process.pid, signal.SIGTERM)
            try:
                await asyncio.wait_for(process.wait(), timeout=2)
            except asyncio.TimeoutError:
                pass
        finally:
            # Leader exit does not prove that its descendants have stopped or closed pipes.
            with suppress(ProcessLookupError):
                os.killpg(process.pid, signal.SIGKILL)
        if process.returncode is None:
            await asyncio.wait_for(process.wait(), timeout=2)
