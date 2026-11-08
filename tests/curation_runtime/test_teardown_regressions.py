"""Reproduce teardown hazards involving in-flight private tools and surviving process descendants."""

import asyncio
import json
import os
from pathlib import Path
import signal

from fastmcp import Client
from fastmcp.client.transports import StreamableHttpTransport
import httpx
import pytest

from runtime_helpers import (ControlledService, assert_cleaned, live_runtime,
                             queued_events, wait_for_marker)


class GatedReadService(ControlledService):
    """Hold an actual private read in service I/O until test cleanup releases it."""

    # Expose entry and release gates for a storage operation waiting on external I/O.
    def __init__(self):
        super().__init__()
        self.read_entered = asyncio.Event()
        self.release_read = asyncio.Event()

    # Simulate provider I/O that holds its wrapper lock and cannot complete until externally released.
    async def read_note(self, note_id):
        self.read_entered.set()
        while not self.release_read.is_set():
            try:
                await self.release_read.wait()
            except asyncio.CancelledError:
                pass
        return await super().read_note(note_id)


# Observe transport authorization without starting another lock-blocked private tool.
async def private_initialize_status(url, token):
    async with httpx.AsyncClient(timeout=1) as client:
        response = await client.post(url + "/internal/mcp", headers={
            "x-tribal-run-token": token, "Accept": "application/json, text/event-stream"},
            json={"jsonrpc": "2.0", "id": 5, "method": "initialize", "params": {
                "protocolVersion": "2025-03-26", "capabilities": {},
                "clientInfo": {"name": "teardown-regression", "version": "1"}}})
    return response.status_code


# Complete cancellation and timeout without waiting indefinitely for an active private read.
@pytest.mark.parametrize("termination", ["cancel", "timeout"])
def test_terminated_run_revokes_token_and_finishes_while_private_read_is_blocked(tmp_path, termination):
    # Keep a genuine private MCP read awaiting storage while terminating its owning run.
    async def exercise():
        service = GatedReadService()
        timeout = 2.5 if termination == "timeout" else 20
        async with live_runtime(tmp_path, mode="hang", service=service,
                                timeout_seconds=timeout) as (curator, _, events, url, marker):
            async with events.subscribe() as queue:
                task = asyncio.create_task(curator.seed_agent_context("blocked storage read", None, None))
                private_task = None
                try:
                    record = await wait_for_marker(marker)
                    token = record["headers"]["x-tribal-run-token"]
                    # Keep an independent private HTTP request alive while its owning child terminates.
                    async def read_private_note():
                        transport = StreamableHttpTransport(url + "/internal/mcp", headers={
                            "x-tribal-run-token": token})
                        async with Client(transport) as client:
                            return await client.call_tool("read_note", {"note_id": "note-a"},
                                                          raise_on_error=False)
                    private_task = asyncio.create_task(read_private_note())
                    await asyncio.wait_for(service.read_entered.wait(), timeout=2)
                    assert await private_initialize_status(url, token) == 200
                    if termination == "cancel":
                        task.cancel()
                    done, _ = await asyncio.wait({task}, timeout=4 if termination == "timeout" else 1)
                    status = await private_initialize_status(url, token)
                    assert status == 403, "Terminated run retained private tool permissions during storage I/O"
                    assert task in done, "Run teardown waited indefinitely for the active private tool"
                    assert not service.release_read.is_set()
                    if termination == "cancel":
                        with pytest.raises(asyncio.CancelledError):
                            await task
                    else:
                        with pytest.raises(Exception):
                            await task
                    assert_cleaned(marker)
                    observed = queued_events(queue)
                    assert observed[-1]["type"] == "run_failed"
                    assert observed[-1]["status"] == "failed"
                    await asyncio.wait_for(curator.close(), timeout=1)
                finally:
                    service.release_read.set()
                    await asyncio.gather(task, *([private_task] if private_task else []),
                                         return_exceptions=True)
    asyncio.run(exercise())


# Distinguish live descendants from dead zombies awaiting the host's orphan reaper.
def process_is_running(pid):
    try:
        status = Path(f"/proc/{pid}/stat").read_text()
    except FileNotFoundError:
        return False
    return status.rsplit(")", 1)[1].strip().split()[0] not in {"Z", "X"}


# Clean a surviving process group even when its original Codex leader already exited.
@pytest.mark.parametrize("mode", ["descendant", "descendant_ignores_term", "descendant_holds_pipes"])
def test_exited_leader_cleanup_reaches_descendants(tmp_path, mode):
    # Launch an actual descendant that closes inherited pipes and outlives its leader.
    async def exercise():
        record = None
        async with live_runtime(tmp_path, mode=mode, final={"context": "No sources.", "sources": []},
                                timeout_seconds=2 if mode == "descendant_holds_pipes" else 10) as (curator, service, events, url, marker):
            try:
                if mode == "descendant_holds_pipes":
                    with pytest.raises(Exception):
                        await curator.seed_agent_context("process group cleanup", None, None)
                else:
                    result = await curator.seed_agent_context("process group cleanup", None, None)
                    assert result == {"context": "No sources.", "sources": []}
                record = json.loads(marker.read_text())
                assert_cleaned(marker)
                descendant = record["descendant_pid"]
                for _ in range(100):
                    if not process_is_running(descendant):
                        break
                    await asyncio.sleep(0.01)
                assert not process_is_running(descendant), (
                    f"Curator leader {record['pid']} exited but descendant {descendant} is still running"
                )
            finally:
                if record is None and marker.exists():
                    record = json.loads(marker.read_text())
                if record is not None:
                    try:
                        os.killpg(record["pid"], signal.SIGKILL)
                    except ProcessLookupError:
                        pass
    asyncio.run(exercise())
