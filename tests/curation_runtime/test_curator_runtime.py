"""Exercise concurrent Codex subprocesses, private MCP permissions, replay and event broadcasts."""

import asyncio
import json

from fastmcp import Client
import httpx
import pytest

from runtime_helpers import (SAVED, assert_cleaned, live_runtime, queued_events,
                             sse_subscription, wait_for_marker)

READ_CALLS = [
    {"name": "search_notes", "arguments": {"query": "guide"}},
    {"name": "read_note", "arguments": {"note_id": "note-a"}},
    {"name": "follow_link", "arguments": {"source_id": "note-a", "target_id": "note-b"}},
    {"name": "get_note_spec", "arguments": {"note_type": "guide"}},
]
WRITE_CALL = {"name": "apply_changes", "arguments": {"changes": [
    {"action": "create", "path": "Guides/Saved.md", "markdown": "# Saved note"}]}}
UNCHANGED = {"status": "unchanged", "message": "Evidence already known.", "notes": []}


# Deny forged and expired permissions through the real mounted private endpoint.
async def assert_token_denied(base_url, token):
    async with httpx.AsyncClient() as client:
        response = await client.post(base_url + "/internal/mcp",
            headers={"x-tribal-run-token": token, "Accept": "application/json, text/event-stream"},
            json={"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {
                "name": "read_note", "arguments": {"note_id": "note-a"}}})
    assert response.status_code in (401, 403)



# Require complete named activity envelopes and prohibit leaked model reasoning.
def assert_event_envelopes(events):
    required = {"type", "run_id", "name", "color", "message", "status", "node_ids", "edge_ids", "timestamp"}
    assert events
    for event in events:
        assert required <= set(event)
        assert event["run_id"] and event["name"] and event["color"]
        assert event["status"] in {"working", "done", "failed"}
        assert "PRIVATE_REASONING_SENTINEL" not in json.dumps(event)


# Verify launched flags, real internal reads, exact observed graph activity and token revocation.
def test_real_executable_reads_notes_and_revokes_private_token(tmp_path):
    # Run the public MCP call over HTTP while the real fake process uses private MCP.
    async def exercise():
        async with live_runtime(tmp_path, calls=READ_CALLS) as (curator, service, events, url, marker):
            await assert_token_denied(url, "forged-token")
            async with events.subscribe() as queue:
                async with Client(url + "/mcp") as client:
                    result = await client.call_tool("seed_agent_context", {"task": "Need guide"})
                observed = queued_events(queue)
            assert json.loads(result.content[0].text) == {"context": "Verified context.", "sources": [
                {"path": "Guides/First.md", "title": "First note"}]}
            record = json.loads(marker.read_text())
            assert set(record["tools"]) == {"search_notes", "read_note", "follow_link", "get_note_spec"}
            assert not service.saved
            assert all(not result["is_error"] for result in record["results"])
            for flag in ("--json", "--ephemeral", "--ignore-user-config", "--skip-git-repo-check", "--output-schema"):
                assert flag in record["argv"]
            assert record["argv"][record["argv"].index("--sandbox") + 1] == "read-only"
            assert record["cwd"] != str(tmp_path)
            assert_event_envelopes(observed)
            assert observed[0]["type"] == "run_started"
            assert observed[-1]["type"] == "run_finished"
            traversals = [event for event in observed if event["edge_ids"]]
            assert len(traversals) == 1
            assert traversals[0]["edge_ids"] == ["note-a--note-b"]
            assert set(traversals[0]["node_ids"]) == {"note-a", "note-b"}
            await assert_token_denied(url, record["headers"]["x-tribal-run-token"])
            assert_cleaned(marker)
    asyncio.run(exercise())


# Enforce context permissions even when an executable directly calls the hidden write tool.
def test_context_run_cannot_publish_even_by_direct_tool_name(tmp_path):
    # Attempt a write and still return a valid empty-source context result.
    async def exercise():
        async with live_runtime(tmp_path, calls=[WRITE_CALL], final={"context": "No edits", "sources": []}) as (curator, service, events, url, marker):
            result = await curator.seed_agent_context("try write", None, None)
            assert result == {"context": "No edits", "sources": []}
            assert not service.saved
            record = json.loads(marker.read_text())
            assert record["results"][0]["is_error"]
            assert "apply_changes" not in record["tools"]
    asyncio.run(exercise())


# Reject a model's claim of a saved update without an actual apply_changes receipt.
def test_updated_result_requires_actual_saved_publication(tmp_path):
    # Return a fabricated success without making any private write call.
    async def exercise():
        async with live_runtime(tmp_path, final={key: SAVED[key] for key in ("status", "message", "notes")}) as (curator, service, events, url, marker):
            with pytest.raises(Exception, match="(?i)(save|publish|receipt|actual)"):
                await curator.update_knowledge_base("invented-save", "some evidence", None, None)
            assert not service.saved
            assert not service.requests
            assert_cleaned(marker)
    asyncio.run(exercise())


# Return a saved note result and replay it without spawning another process or writing twice.
def test_saved_result_replays_and_changed_payload_is_rejected(tmp_path):
    # Perform one real private publication followed by identical and conflicting requests.
    async def exercise():
        final = {"status": "updated", "message": "Model wording", "notes": SAVED["notes"]}
        async with live_runtime(tmp_path, calls=[WRITE_CALL], final=final) as (curator, service, events, url, marker):
            first = await curator.update_knowledge_base("publish-once", "verified evidence", None, None)
            before = marker.read_bytes()
            second = await curator.update_knowledge_base("publish-once", "verified evidence", None, None)
            assert first == second
            assert first["status"] == "updated" and first["notes"] == [{"path": "Guides/Saved.md", "action": "created"}]
            assert len(service.saved) == 1
            assert marker.read_bytes() == before
            assert "saved-note" in service.notes
            with pytest.raises(Exception, match="(?i)(conflict|payload|reus|different)"):
                await curator.update_knowledge_base("publish-once", "changed evidence", None, None)
            with pytest.raises(Exception, match="(?i)(conflict|payload|reus|different)"):
                await curator.update_knowledge_base("publish-once", "verified evidence", "repo-b", None)
            assert len(service.saved) == 1
            assert set(json.loads(marker.read_text())["tools"]) == {
                "search_notes", "read_note", "follow_link", "get_note_spec", "apply_changes"}
    asyncio.run(exercise())


# Start two independent update processes before releasing either, proving runs are concurrent.
def test_distinct_update_requests_run_concurrently(tmp_path):
    # Hold every child at a filesystem barrier until two run starts have arrived.
    async def exercise():
        release = tmp_path / "release"
        async with live_runtime(tmp_path, final=UNCHANGED, release=release) as (curator, service, events, url, marker):
            async with events.subscribe() as queue:
                first = asyncio.create_task(curator.update_knowledge_base("parallel-a", "evidence a", None, None))
                second = asyncio.create_task(curator.update_knowledge_base("parallel-b", "evidence b", None, None))
                try:
                    started = []
                    for _ in range(2):
                        started.append(await asyncio.wait_for(queue.get(), timeout=2))
                    assert all(event["type"] == "run_started" for event in started)
                    assert len({event["run_id"] for event in started}) == 2
                    assert len({event["name"] for event in started}) == 2
                    for _ in range(300):
                        if len(list(tmp_path.glob("codex-observed-pid-*.json"))) == 2:
                            break
                        await asyncio.sleep(0.01)
                    assert len(list(tmp_path.glob("codex-observed-pid-*.json"))) == 2, "Second curator subprocess was serialized"
                    assert not first.done() and not second.done()
                    release.write_text("go")
                    assert await asyncio.wait_for(first, 10) == UNCHANGED
                    assert await asyncio.wait_for(second, 10) == UNCHANGED
                finally:
                    release.write_text("go")
                    await asyncio.gather(first, second, return_exceptions=True)
            assert set(service.requests) == {"parallel-a", "parallel-b"}
    asyncio.run(exercise())


# Serialize duplicate in-flight request IDs while still returning one stable publication result.
def test_simultaneous_identical_requests_publish_once(tmp_path):
    # Race two same-ID calls through a controlled child release barrier.
    async def exercise():
        release = tmp_path / "release"
        final = {key: SAVED[key] for key in ("status", "message", "notes")}
        async with live_runtime(tmp_path, calls=[WRITE_CALL], final=final, release=release) as (curator, service, events, url, marker):
            first = asyncio.create_task(curator.update_knowledge_base("same-id", "evidence", None, None))
            second = asyncio.create_task(curator.update_knowledge_base("same-id", "evidence", None, None))
            try:
                await wait_for_marker(marker)
                release.write_text("go")
                results = await asyncio.wait_for(asyncio.gather(first, second), 10)
            finally:
                release.write_text("go")
                await asyncio.gather(first, second, return_exceptions=True)
            assert results[0] == results[1]
            assert len(service.saved) == 1
            assert len(list(tmp_path.glob("codex-observed-pid-*.json"))) == 1
    asyncio.run(exercise())


# Reap failing, timed-out and cancelled children and invalidate their captured permissions.
@pytest.mark.parametrize("mode", ["fail", "timeout", "cancel"])
def test_process_failure_timeout_cancel_cleanup(tmp_path, mode):
    # Observe the child PID before causing each terminal path.
    async def exercise():
        child_mode = "fail" if mode == "fail" else "hang"
        timeout = 0.8 if mode == "timeout" else 10
        async with live_runtime(tmp_path, mode=child_mode, timeout_seconds=timeout) as (curator, service, events, url, marker):
            async with events.subscribe() as queue:
                task = asyncio.create_task(curator.seed_agent_context("terminal path", None, None))
                record = await wait_for_marker(marker)
                if mode == "cancel":
                    task.cancel()
                    with pytest.raises(asyncio.CancelledError):
                        await task
                else:
                    with pytest.raises(Exception):
                        await task
                observed = queued_events(queue)
            assert observed[-1]["type"] == "run_failed"
            assert observed[-1]["status"] == "failed"
            assert_event_envelopes(observed)
            assert_cleaned(marker)
            await assert_token_denied(url, record["headers"]["x-tribal-run-token"])
    asyncio.run(exercise())


# Broadcast actual activity to two browsers and keep serving after one disconnects.
def test_sse_broadcast_disconnect_and_graph_snapshot(tmp_path):
    # Connect two independent HTTP streams and compare the run's delivered envelopes.
    async def exercise():
        async with live_runtime(tmp_path, calls=READ_CALLS) as (curator, service, events, url, marker):
            async with httpx.AsyncClient() as client:
                response = await client.get(url + "/api/graph")
                assert response.status_code == 200
                graph = response.json()
                assert graph["project_id"] == "runtime-test"
                assert {node["id"] for node in graph["nodes"]} == {"note-a", "note-b"}
                assert graph["edges"] == [{"id": "note-a--note-b", "source": "note-a", "target": "note-b"}]
                assert (await client.get(url + "/healthz")).is_success
            async with sse_subscription(url) as first:
                async with sse_subscription(url) as second:
                    await curator.seed_agent_context("broadcast", None, None)
                    for _ in range(100):
                        if first and second and first[-1]["type"] == second[-1]["type"] == "run_finished":
                            break
                        await asyncio.sleep(0.01)
                    assert first == second
                    assert_event_envelopes(first)
                    assert first[-1]["type"] == "run_finished"
                count = len(first)
                await curator.seed_agent_context("after disconnect", None, None)
                for _ in range(100):
                    if len(first) > count and first[-1]["type"] == "run_finished":
                        break
                    await asyncio.sleep(0.01)
                assert len(first) > count
                assert first[-1]["type"] == "run_finished"
    asyncio.run(exercise())


# Never forward backend or embedding credentials into the curator subprocess environment.
def test_curator_child_does_not_receive_storage_or_embedding_secrets(tmp_path, monkeypatch):
    # Seed representative backend credentials and inspect what the real child receives.
    async def exercise():
        for name in ("OPENAI_API_KEY", "AWS_SECRET_ACCESS_KEY", "TRIBAL_MYSQL_PASSWORD"):
            monkeypatch.setenv(name, "runtime-test-secret-must-not-reach-child")
        async with live_runtime(tmp_path, final={"context": "Empty", "sources": []}) as (curator, service, events, url, marker):
            await curator.seed_agent_context("no secret forwarding", None, None)
            assert json.loads(marker.read_text())["leaked_secrets"] == {}
    asyncio.run(exercise())


# Reconcile a saved write after process failure instead of applying the same change again.
def test_retry_after_child_failure_recovers_actual_saved_result(tmp_path):
    # Kill the controlled process after its private write has already published.
    async def exercise():
        async with live_runtime(tmp_path, calls=[WRITE_CALL], final=UNCHANGED, mode="fail_after_tools") as (curator, service, events, url, marker):
            with pytest.raises(Exception):
                await curator.update_knowledge_base("recover-save", "verified evidence", None, None)
            assert len(service.saved) == 1
            result = await curator.update_knowledge_base("recover-save", "verified evidence", None, None)
            assert result["status"] == "updated"
            assert result["notes"] == [{"path": "Guides/Saved.md", "action": "created"}]
            assert len(service.saved) == 1
            assert len(list(tmp_path.glob("codex-observed-pid-*.json"))) == 1
    asyncio.run(exercise())


# Reject sources that the process never actually read through the KB tools.
def test_context_cannot_cite_unread_note(tmp_path):
    # Return an existing note's path without using any read tool.
    async def exercise():
        async with live_runtime(tmp_path) as (curator, service, events, url, marker):
            with pytest.raises(Exception, match="(?i)(read|source|evidence)"):
                await curator.seed_agent_context("invented citation", None, None)
            assert_cleaned(marker)
    asyncio.run(exercise())


# Emit no graph traversal when a guessed edge fails verification in the service.
def test_invalid_follow_link_emits_no_edge_highlight(tmp_path):
    # Try traversing the reverse of the only existing directed edge.
    async def exercise():
        calls = [{"name": "follow_link", "arguments": {"source_id": "note-b", "target_id": "note-a"}}]
        async with live_runtime(tmp_path, calls=calls, final={"context": "No verified edge.", "sources": []}) as (curator, service, events, url, marker):
            async with events.subscribe() as queue:
                await curator.seed_agent_context("invalid edge", None, None)
                observed = queued_events(queue)
            assert json.loads(marker.read_text())["results"][0]["is_error"]
            assert all(not event["edge_ids"] for event in observed)
    asyncio.run(exercise())


# Reject malformed structured final output rather than treating it as an empty successful run.
@pytest.mark.parametrize("final", [
    {"context": "Missing source list"},
    {"context": 42, "sources": []},
    {"context": "Unknown output", "sources": [], "unexpected": "field"},
])
def test_context_final_result_schema_is_enforced(tmp_path, final):
    # Return each independently malformed result from an otherwise successful child.
    async def exercise():
        async with live_runtime(tmp_path, final=final) as (curator, service, events, url, marker):
            with pytest.raises(Exception):
                await curator.seed_agent_context("bad schema", None, None)
            assert_cleaned(marker)
    asyncio.run(exercise())


# Recover the final agent JSON from actual JSONL when the CLI omits its output file.
def test_jsonl_final_agent_message_fallback(tmp_path):
    # Produce normal JSONL events with no --output-last-message artifact.
    async def exercise():
        async with live_runtime(tmp_path, final={"context": "JSONL context.", "sources": []}, mode="jsonl_only") as (curator, service, events, url, marker):
            assert await curator.seed_agent_context("jsonl fallback", None, None) == {
                "context": "JSONL context.", "sources": []}
            assert_cleaned(marker)
    asyncio.run(exercise())


# Bound a lagging subscriber while delivering current events to a second active subscriber.
def test_activity_bus_bounded_broadcast_and_disconnect():
    # Flood one browser queue and then ensure later subscriptions still receive activity.
    async def exercise():
        from tribal_kb.activity import ActivityBus
        bus = ActivityBus(queue_size=2)
        async with bus.subscribe() as slow:
            async with bus.subscribe() as fast:
                for sequence in range(5):
                    await bus.publish({"message": str(sequence)})
                    assert (await fast.get())["message"] == str(sequence)
                assert slow.qsize() <= 2
                assert (await slow.get())["message"] == "3"
                assert (await slow.get())["message"] == "4"
            await bus.publish({"message": "after disconnect"})
            assert (await slow.get())["message"] == "after disconnect"
            assert fast.empty(), "Disconnected subscriber is still being enqueued"
    asyncio.run(exercise())
