"""Provide controlled service state and real executable/HTTP resources for runtime tests."""

import asyncio
from contextlib import asynccontextmanager
import importlib
import json
import os
from pathlib import Path
import socket
import sys

import httpx
import uvicorn

NOTE = {"id": "note-a", "title": "First note", "type": "guide", "path": "Guides/First.md",
        "markdown": "# First note\n\n[[Second]]", "revision": 1,
        "links": [{"id": "note-a--note-b", "source": "note-a", "target": "note-b"}]}
TARGET = {"id": "note-b", "title": "Second note", "type": "guide", "path": "Guides/Second.md",
          "markdown": "# Second note", "revision": 1, "links": []}
SAVED = {"status": "updated", "message": "Saved a real controlled revision.",
         "notes": [{"path": "Guides/Saved.md", "action": "created"}], "issues": []}


class ControlledService:
    """Implement the agreed service port with observable publication and replay state."""

    # Begin with two linked notes and an empty publication ledger.
    def __init__(self):
        self.project_id = "runtime-test"
        self.notes = {"note-a": dict(NOTE), "note-b": dict(TARGET)}
        self.saved = []
        self.requests = {}

    # Search only the project's controlled published documents.
    async def search_notes(self, query, limit=10):
        return [{key: note[key] for key in ("id", "title", "path")} | {"excerpt": "context"}
                for note in self.notes.values()][:limit]

    # Read a published document by its stable ID.
    async def read_note(self, note_id):
        return self.notes[note_id]

    # Reject invented links before returning the verified target document.
    async def follow_link(self, source_id, target_id):
        if not any(link["target"] == target_id for link in self.notes[source_id]["links"]):
            raise ValueError("No verified link exists")
        return self.notes[target_id]

    # Return specification text for an explicitly supported note type.
    async def get_note_spec(self, note_type):
        if note_type != "guide":
            raise ValueError("Unsupported note type")
        return "Guide notes require project scope and a purpose."

    # Publish a controlled note and persist the actual result for replay reconciliation.
    async def apply_changes(self, changes, *, request_id=None, request_hash=None):
        self.saved.extend(changes)
        for change in changes:
            self.notes["saved-note"] = {"id": "saved-note", "title": "Saved note", "type": "guide",
                "path": change["path"], "markdown": change.get("markdown", ""), "revision": 1,
                "links": []}
        result = dict(SAVED)
        if request_id is not None:
            await self.remember_request_result(request_id, request_hash, result)
        return result

    # Return the current published graph rather than process-generated claims.
    async def graph(self):
        return {"project_id": self.project_id,
            "nodes": [{key: note[key] for key in ("id", "title", "type", "path")}
                      for note in self.notes.values()], "edges": list(NOTE["links"])}

    # Look up a completed request while rejecting reused IDs with changed evidence.
    async def get_request_result(self, request_id, request_hash):
        prior = self.requests.get(request_id)
        if prior is not None and prior[0] != request_hash:
            raise ValueError("Request ID reused with conflicting payload")
        return None if prior is None else prior[1]

    # Persist a completed outcome with the exact payload identity used at publication.
    async def remember_request_result(self, request_id, request_hash, result):
        await self.get_request_result(request_id, request_hash)
        self.requests[request_id] = (request_hash, result)


# Create a real executable with scenario data outside the disposable curator workspace.
def make_executable(tmp_path, *, calls=(), final=None, mode=None, release=None, label="codex"):
    marker = tmp_path / f"{label}-observed.json"
    scenario_path = tmp_path / f"{label}-scenario.json"
    scenario_path.write_text(json.dumps({"marker": str(marker), "calls": calls,
        "final": final or {"context": "Verified context.", "sources": [
            {"path": "Guides/First.md", "title": "First note"}]}, "mode": mode,
        "release": str(release) if release else None}))
    source = Path(__file__).with_name("fake_codex.py").read_text()
    script = tmp_path / f"{label}-executable"
    script.write_text(f"#!{sys.executable}\n" + source.replace("__SCENARIO_PATH__", str(scenario_path)))
    script.chmod(0o700)
    return script, marker


# Wait for observable subprocess startup without slowing passing tests unnecessarily.
async def wait_for_marker(marker):
    for _ in range(300):
        if marker.exists():
            try:
                return json.loads(marker.read_text())
            except json.JSONDecodeError:
                pass
        await asyncio.sleep(0.01)
    raise AssertionError(f"Curator subprocess did not start: {marker}")


# Run real uvicorn on an ephemeral loopback socket and always release server resources.
@asynccontextmanager
async def live_runtime(tmp_path, *, calls=(), final=None, mode=None, release=None,
                       timeout_seconds=10, label="codex", service=None, model=None):
    server = importlib.import_module("server")
    runtime = importlib.import_module("tribal_kb.runtime")
    activity = importlib.import_module("tribal_kb.activity")
    service = service or ControlledService()
    events = activity.ActivityBus()
    executable, marker = make_executable(tmp_path, calls=calls, final=final, mode=mode,
                                         release=release, label=label)
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    sock.listen(128)
    base_url = f"http://127.0.0.1:{sock.getsockname()[1]}"
    curator = runtime.CodexCurator(service, events, codex_bin=str(executable),
        internal_url=base_url + "/internal/mcp", timeout_seconds=timeout_seconds, model=model)
    app = server.create_app(service=service, curator=curator, events=events)
    runner = uvicorn.Server(uvicorn.Config(app, log_level="error", lifespan="on"))
    task = asyncio.create_task(runner.serve(sockets=[sock]))
    try:
        for _ in range(300):
            if runner.started:
                break
            if task.done():
                await task
            await asyncio.sleep(0.01)
        assert runner.started, "ASGI runtime failed to start"
        yield curator, service, events, base_url, marker
    finally:
        runner.should_exit = True
        try:
            await asyncio.wait_for(task, timeout=5)
        finally:
            sock.close()


# Collect independent SSE events while exposing when response headers are ready.
@asynccontextmanager
async def sse_subscription(base_url):
    events = []
    opened = asyncio.Event()
    # Read the public event stream until its owning context disconnects.
    async def consume():
        async with httpx.AsyncClient(timeout=None) as client:
            async with client.stream("GET", base_url + "/api/activity") as response:
                response.raise_for_status()
                assert "text/event-stream" in response.headers["content-type"]
                opened.set()
                async for line in response.aiter_lines():
                    if line.startswith("data:"):
                        events.append(json.loads(line[5:].strip()))
    task = asyncio.create_task(consume())
    try:
        await asyncio.wait_for(opened.wait(), timeout=3)
        yield events
    finally:
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass


# Drain already published bus events after a run completes.
def queued_events(queue):
    result = []
    while not queue.empty():
        result.append(queue.get_nowait())
    return result


# Require a terminated process and removed isolated working directory.
def assert_cleaned(marker):
    record = json.loads(marker.read_text())
    assert not Path(record["cwd"]).exists(), "Curator working directory was retained"
    try:
        os.kill(record["pid"], 0)
    except ProcessLookupError:
        return
    raise AssertionError("Curator subprocess is still alive")
