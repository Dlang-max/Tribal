"""Verify durable replay across real service, curator processes, and private HTTP tools."""

import json
from pathlib import Path
import sys

from fastmcp import Client
import pytest

from conftest import NOTE_PATHS

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "curation_runtime"))
from runtime_helpers import live_runtime


# Keep terminal curator outcomes authoritative when private apply publishes no Markdown.
@pytest.mark.asyncio
@pytest.mark.parametrize("apply_kind", ["empty", "already_matching"])
@pytest.mark.parametrize("final", [
    {"status": "needs_information", "message": "Please supply the missing source evidence.", "notes": []},
    {"status": "unchanged", "message": "Reviewed evidence; the existing notes cover it.", "notes": []},
], ids=["needs_information", "unchanged"])
async def test_noop_apply_replays_final_curator_outcome(
    tmp_path, make_service, changes, documents, apply_kind, final,
):
    service, objects, catalog = make_service()
    applied = []
    if apply_kind == "already_matching":
        assert (await service.apply_changes(changes))["status"] == "updated"
        await service.drain_indexing()
        path = NOTE_PATHS["finding"]
        applied = [{"action": "update", "path": path, "expected_revision": 1,
                    "markdown": documents[path]}]
    before = catalog.list_notes(service.project_id)
    history_count, object_count = len(catalog.history), len(objects.objects)
    call = {"name": "apply_changes", "arguments": {"changes": applied}}
    arguments = {"request_id": "no-change-request", "content": "Review the supplied evidence."}
    async with live_runtime(tmp_path, service=service, calls=[call], final=final) as resources:
        _, _, _, url, marker = resources
        async with Client(url + "/mcp") as client:
            first = await client.call_tool("update_knowledge_base", arguments)
            replay = await client.call_tool("update_knowledge_base", arguments)
        observed = json.loads(marker.read_text())["results"]
        assert len(observed) == 1 and not observed[0]["is_error"]
        assert observed[0]["data"]["status"] == "unchanged"
        assert observed[0]["data"]["notes"] == []
        assert json.loads(first.content[0].text) == final
        assert json.loads(replay.content[0].text) == final
        assert len(list(tmp_path.glob("codex-observed-pid-*.json"))) == 1
    reloaded, _, _ = make_service(objects=objects, catalog=catalog)
    async with live_runtime(tmp_path, service=reloaded, label="replay") as resources:
        curator, _, _, _, marker = resources
        assert await curator.update_knowledge_base(**arguments) == final
        assert not marker.exists(), "Durable replay must not launch another curator"
        with pytest.raises(ValueError, match="hash conflict"):
            await curator.update_knowledge_base(arguments["request_id"], "Different evidence.")
    assert catalog.list_notes(service.project_id) == before
    assert len(catalog.history) == history_count
    assert len(objects.objects) == object_count


# Recover an actual publication after a no-op and child failure without rerunning writes.
@pytest.mark.asyncio
async def test_noop_then_published_changes_recover_after_child_failure(tmp_path, make_service, changes):
    service, objects, catalog = make_service()
    calls = [{"name": "apply_changes", "arguments": {"changes": batch}}
             for batch in ([], changes)]
    async with live_runtime(
        tmp_path, service=service, calls=calls, mode="fail_after_tools",
    ) as resources:
        curator, _, _, _, marker = resources
        with pytest.raises(Exception, match="codex exited with status 24"):
            await curator.update_knowledge_base("published-request", "Verified publication evidence.")
        observed = json.loads(marker.read_text())["results"]
        assert all(not result["is_error"] for result in observed)
        assert [result["data"]["status"] for result in observed] == ["unchanged", "updated"]
        result = await curator.update_knowledge_base("published-request", "Verified publication evidence.")
        assert result["status"] == "updated"
        assert result["message"] == "Published validated notes"
        assert result["notes"] == [{"path": change["path"], "action": "created"} for change in changes]
        assert len(list(tmp_path.glob("codex-observed-pid-*.json"))) == 1
    assert len(catalog.history) == len(objects.objects) == len(changes) == 11
    assert all(note["revision"] == 1 for note in catalog.list_notes(service.project_id))
