"""Verify HTTP embedding validation and revision-safe optional semantic indexing."""
import asyncio
import importlib
import json

import httpx
import pytest

from conftest import NOTE_PATHS
from test_service_contract import updated_change


# Build the public HTTP embedding client without any live API calls.
def embedding_client(http_client=None, **kwargs):
    cls = importlib.import_module("tribal_kb.embeddings").OpenAIEmbeddingClient
    return cls("unit-test-key", http_client=http_client, **kwargs)


# Exercise real HTTPX request serialization and restore response order by index.
@pytest.mark.asyncio
async def test_http_embedding_request_and_indexed_response_order():
    requests = []

    # Inspect the serialized provider boundary and return deliberately reordered results.
    def respond(request):
        requests.append(request)
        assert request.method == "POST"
        assert str(request.url) == "https://api.openai.com/v1/embeddings"
        assert request.headers["authorization"] == "Bearer unit-test-key"
        assert json.loads(request.content) == {
            "model": "text-embedding-3-small", "input": ["first", "second"], "dimensions": 2,
        }
        return httpx.Response(200, json={"model": "text-embedding-3-small", "data": [
            {"index": 1, "embedding": [0.0, 1.0]}, {"index": 0, "embedding": [1.0, 0.0]},
        ]})

    async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as http:
        client = embedding_client(http, dimensions=2)
        assert await client.embed(["first", "second"]) == [[1.0, 0.0], [0.0, 1.0]]
    assert len(requests) == 1


# Refuse provider responses outside the pinned model, dimension, or finite vector space.
@pytest.mark.asyncio
@pytest.mark.parametrize("response", [
    {"model": "other-model", "data": [{"index": 0, "embedding": [1, 0]}]},
    {"model": "text-embedding-3-small", "data": [{"index": 0, "embedding": [1]}]},
    {"model": "text-embedding-3-small", "data": []},
    {"model": "text-embedding-3-small", "data": [{"index": 1, "embedding": [1, 0]}]},
    {"model": "text-embedding-3-small", "data": [{"index": 0, "embedding": [True, 0]}]},
    {"model": "text-embedding-3-small", "data": [{"index": 0, "embedding": ["1", 0]}]},
    {"model": "text-embedding-3-small", "data": [{"index": 0, "embedding": [float("nan"), 0]}]},
    {"model": "text-embedding-3-small", "data": [{"index": 0, "embedding": [float("inf"), 0]}]},
])
async def test_http_rejects_invalid_vectors(response):
    # Encode raw response bytes so nonfinite JSON cannot be hidden by HTTPX serialization.
    def respond(request):
        return httpx.Response(200, content=json.dumps(response), headers={"Content-Type": "application/json"})

    async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as http:
        with pytest.raises(ValueError):
            await embedding_client(http, dimensions=2).embed(["one"])


# Preserve HTTP dependency errors so callers can report them accurately.
@pytest.mark.asyncio
async def test_http_provider_failure_is_an_error():
    # Return a provider rate-limit response through a real HTTPX transport.
    def respond(request):
        return httpx.Response(429, json={"error": {"message": "rate limited"}})

    async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as http:
        with pytest.raises(httpx.HTTPStatusError):
            await embedding_client(http, dimensions=2).embed(["one"])


# Keep an unconfigured provider unavailable and make no outgoing request.
@pytest.mark.asyncio
async def test_missing_key_is_lexical_only_and_makes_no_http_call(monkeypatch, make_service, changes):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    # Fail immediately if lexical-only mode tries to reach the HTTP boundary.
    def unexpected_request(request):
        raise AssertionError("Missing API key must not fabricate embeddings or send HTTP")

    async with httpx.AsyncClient(transport=httpx.MockTransport(unexpected_request)) as http:
        cls = importlib.import_module("tribal_kb.embeddings").OpenAIEmbeddingClient
        client = cls(http_client=http)
        assert client.available is False
        service, _, catalog = make_service(embedding=client)
        assert (await service.apply_changes(changes))["status"] == "updated"
        await service.drain_indexing()
        chunks = catalog.list_chunks("checkout-demo")
        assert chunks
        assert all(chunk.get("vector") is None for chunk in chunks)
        assert await service.search_notes("discount")


# Make a failed HTTP index request harmless to durable core note publication.
@pytest.mark.asyncio
async def test_failed_embedding_http_keeps_write_and_lexical_search(make_service, changes):
    # Return a provider outage for indexing and query embedding alike.
    def respond(request):
        return httpx.Response(503, json={"error": "provider down"})

    async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as http:
        service, _, catalog = make_service(embedding=embedding_client(http, dimensions=2))
        assert (await service.apply_changes(changes))["status"] == "updated"
        await service.drain_indexing()
        assert (await service.read_note("finding-note-demo"))["revision"] == 1
        assert all(chunk.get("vector") is None for chunk in catalog.list_chunks("checkout-demo"))
        assert await service.search_notes("discount")


class DelayedEmbeddings:
    model = "test-space"
    dimensions = 2
    available = True

    # Expose explicit provider gates so writes can be tested without timing sleeps.
    def __init__(self):
        self.started = asyncio.Event()
        self.release = asyncio.Event()

    # Delay results until newer source revisions have had a chance to publish.
    async def embed(self, texts):
        self.started.set()
        await self.release.wait()
        return [[1.0, 0.0] for _ in texts]


# Release delayed vectors only after another curator has published a newer revision.
@pytest.mark.asyncio
async def test_delayed_embeddings_do_not_hold_publication_lock_or_attach_stale_results(make_service, changes, documents):
    client = DelayedEmbeddings()
    first, objects, catalog = make_service(embedding=client)
    second, _, _ = make_service(objects=objects, catalog=catalog)
    try:
        result = await asyncio.wait_for(first.apply_changes(changes), timeout=2)
        assert result["status"] == "updated"
        await asyncio.wait_for(client.started.wait(), timeout=2)
        update = updated_change(documents, suffix="Newer content published during delayed HTTP.")
        assert (await asyncio.wait_for(second.apply_changes([update]), timeout=2))["status"] == "updated"
        await second.drain_indexing()
    finally:
        client.release.set()
        await first.drain_indexing()
    assert (await second.read_note("finding-note-demo"))["revision"] == 2
    finding_chunks = [c for c in catalog.list_chunks("checkout-demo") if c["note_id"] == "finding-note-demo"]
    assert finding_chunks
    assert {chunk["revision"] for chunk in finding_chunks} == {2}
    assert all(chunk["vector"] is None for chunk in finding_chunks)
    assert any(project == "checkout-demo" and note_id == "finding-note-demo" and revision == 1
               for project, note_id, revision in catalog.replace_attempts)


# Rank semantically matching current vectors while excluding stale or incompatible caches.
@pytest.mark.asyncio
async def test_semantic_search_ignores_stale_model_dimension_and_archived_vectors(make_service, changes):
    client = DelayedEmbeddings()
    client.release.set()
    service, objects, catalog = make_service()
    await service.apply_changes(changes)
    await service.drain_indexing()
    service_with_vectors, _, _ = make_service(objects=objects, catalog=catalog, embedding=client)
    fresh = {
        "note_id": "finding-note-demo", "revision": 1, "position": 0, "heading": "Overview",
        "text": "Expired Code Accepted", "content_hash": "stored-source-hash", "model": "test-space",
        "dimensions": 2, "vector": [1.0, 0.0],
    }
    catalog.chunks = {("checkout-demo", "finding-note-demo"): [fresh]}
    assert [r["id"] for r in await service_with_vectors.search_notes("quuxsemanticprobe")] == ["finding-note-demo"]
    for mutation in [{"revision": 0}, {"model": "old-space"}, {"dimensions": 3}, {"vector": [float("nan"), 0]}]:
        catalog.chunks = {("checkout-demo", "finding-note-demo"): [fresh | mutation]}
        assert await service_with_vectors.search_notes("quuxsemanticprobe") == []
    catalog.chunks = {("checkout-demo", "finding-note-demo"): [fresh]}
    await service.apply_changes([{"action": "archive", "path": NOTE_PATHS["finding"], "expected_revision": 1}])
    assert await service_with_vectors.search_notes("quuxsemanticprobe") == []


# Verify indexed source chunks carry the exact revision and configured vector metadata.
@pytest.mark.asyncio
async def test_successful_index_persists_overview_heading_and_source_metadata(make_service, changes):
    client = DelayedEmbeddings()
    client.release.set()
    service, _, catalog = make_service(embedding=client)
    await service.apply_changes(changes)
    await service.drain_indexing()
    chunks = catalog.list_chunks("checkout-demo")
    assert {chunk["note_id"] for chunk in chunks} == {note["id"] for note in catalog.list_notes("checkout-demo")}
    for note in catalog.list_notes("checkout-demo"):
        note_chunks = [chunk for chunk in chunks if chunk["note_id"] == note["id"]]
        assert len(note_chunks) > 1
        assert any("overview" in chunk["heading"].lower() for chunk in note_chunks)
        assert all(chunk["revision"] == 1 and chunk["model"] == "test-space" and chunk["dimensions"] == 2 for chunk in note_chunks)
        assert all(chunk["text"] and chunk["content_hash"] and chunk["vector"] == [1.0, 0.0] for chunk in note_chunks)
        assert len({chunk["position"] for chunk in note_chunks}) == len(note_chunks)
