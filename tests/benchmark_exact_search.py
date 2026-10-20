"""Controlled real-DB exact-search benchmark; never reads provider credentials.

Run with PYTHONPATH=/path/to/checkout/src and TRIBAL_TEST_MYSQL_CONFIG JSON.
This measures the public search path, including DB vector scan, exact scoring,
rank materialization and first-page provenance. The deterministic provider isolates
retrieval cost from external network latency. Results are machine-specific.
"""
from __future__ import annotations

import argparse
import json
import math
import os
import random
import statistics
import struct
import time
import tracemalloc
import uuid
from pathlib import Path

from acceptance_helpers import execute, note

DIMENSIONS = 1536
QUERY = "How do seed conditions influence early germination?"


def roundtrip(values):
    scale = max(abs(value) for value in values)
    scaled = [value / scale for value in values]
    norm = math.sqrt(math.fsum(value * value for value in scaled))
    normalized = [value / norm for value in scaled]
    return list(struct.unpack("<" + "f" * DIMENSIONS, struct.pack("<" + "f" * DIMENSIONS, *normalized)))


def cosine(left, right):
    dot = math.fsum(a * b for a, b in zip(left, right))
    norm_left = math.sqrt(math.fsum(value * value for value in left))
    norm_right = math.sqrt(math.fsum(value * value for value in right))
    return dot / (norm_left * norm_right)


def run_benchmark(config, *, documents=1000, trials=5):
    if documents < 2 or trials < 1:
        raise ValueError("benchmark requires at least 2 documents and 1 trial")
    from tribal.storage import Database, ensure_domain, ensure_knowledge_base, ensure_profile, migrate
    from tribal.publication import ingest_vault
    from tribal.embeddings import activate_profile, format_document_input, input_hash
    from tribal.errors import TribalError
    from tribal.retrieval import search

    db = Database(**config)
    try:
        migrate(db)
        key = "benchmark-" + uuid.uuid4().hex
        kb = ensure_knowledge_base(db, key=key, name="Controlled exact search benchmark")["knowledge_base"]
        ensure_domain(db, knowledge_base=key, key="research", name="Research")
        profile = ensure_profile(db)["profile"]
        assert profile["dimensions"] == DIMENSIONS
        activate_profile(db, knowledge_base=key, profile_id=profile["id"])
        random_source = random.Random(947)
        query_raw = [random_source.uniform(-1, 1) for _ in range(DIMENSIONS)]
        query_vector = roundtrip(query_raw)
        corpus, vectors, identities = {}, {}, {}
        for index in range(documents):
            identity = str(uuid.uuid5(uuid.UUID(kb["id"]), str(index)))
            path = f"observation-{index:06}.md"
            body = f"Seed observation {index}: controlled benchmark source.\n"
            corpus[path] = note(body, id=identity, knowledge_base=key)
            # Duplicate the first direction once to include a true score tie.
            vector = vectors["observation-000000.md"] if index == 1 else roundtrip([random_source.uniform(-1, 1) for _ in range(DIMENSIONS)])
            vectors[path], identities[path] = vector, identity
        heads = {}
        items = list(corpus.items())
        for start in range(0, documents, 100):
            result = ingest_vault(db, dict(items[start:start + 100]), knowledge_base=key)
            assert result["ok"] is True
            heads.update(result["documents"])
        with db.transaction() as connection:
            cursor = connection.cursor()
            try:
                values = []
                for index in range(documents):
                    path = f"observation-{index:06}.md"
                    body = f"Seed observation {index}: controlled benchmark source.\n"
                    digest = input_hash(format_document_input("Seed observations", [], body))
                    values.append((heads[path]["chunk_ids"][0], uuid.UUID(profile["id"]).bytes,
                                   DIMENSIONS, json.dumps(vectors[path]), bytes.fromhex(digest)))
                cursor.executemany("INSERT INTO chunk_embeddings(chunk_id,profile_id,dimensions,embedding,input_hash) VALUES (%s,%s,%s,STRING_TO_VECTOR(%s),%s)", values)
            finally:
                cursor.close()
        expected = sorted([(identities[path], cosine(query_vector, vector)) for path, vector in vectors.items()],
                          key=lambda item: (-item[1], uuid.UUID(item[0]).bytes))
        class Provider:
            calls = 0
            def embed(self, text, *, model, dimensions):
                assert text == QUERY and dimensions == DIMENSIONS
                self.calls += 1
                return query_raw
        provider = Provider()
        durations = []
        peaks = []
        for _ in range(trials):
            tracemalloc.start()
            started = time.perf_counter()
            response = search(db, QUERY, knowledge_base=key, provider=provider, limit=100, max_candidates=documents)
            durations.append(time.perf_counter() - started)
            _, peak = tracemalloc.get_traced_memory()
            tracemalloc.stop()
            peaks.append(peak)
            hits = response["hits"]
            assert [hit["document_id"] for hit in hits] == [identity for identity, _ in expected[:100]]
            assert all(abs(hit["score"] - score) <= 1e-12 for hit, (_, score) in zip(hits, expected))
            assert response["indexing"]["embedded"] == documents
        sessions = execute(db, "SELECT result_count FROM search_sessions WHERE knowledge_base_id=%s", (uuid.UUID(kb["id"]).bytes,))
        assert len(sessions) == trials and all(row["result_count"] == documents for row in sessions)
        try:
            search(db, QUERY, knowledge_base=key, provider=provider, max_candidates=documents - 1)
        except TribalError as error:
            assert error.code == "E_SEARCH_CAPACITY"
        else:
            raise AssertionError("capacity guard silently accepted an incomplete scan")
        ordered = sorted(durations)
        return dict(documents=documents, eligible_vectors=documents, dimensions=DIMENSIONS,
                    trials=trials, provider="deterministic fixed query vector; no live API",
                    scope="public semantic search including DB scan, exact ranking, session materialization and page provenance",
                    exact_top_k_verified=min(100, documents), materialized_results_per_session=documents,
                    latency_seconds=durations, p50_seconds=statistics.median(durations),
                    p95_seconds=ordered[math.ceil(0.95 * len(ordered)) - 1],
                    peak_tracemalloc_bytes=max(peaks), capacity_error_verified="E_SEARCH_CAPACITY",
                    complete=True)
    finally:
        if tracemalloc.is_tracing():
            tracemalloc.stop()
        db.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--documents", type=int, default=1000)
    parser.add_argument("--trials", type=int, default=5)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    raw = os.environ.get("TRIBAL_TEST_MYSQL_CONFIG")
    if raw is None:
        parser.error("set TRIBAL_TEST_MYSQL_CONFIG to isolated real MySQL connector JSON")
    config = json.loads(raw)
    result = run_benchmark(config, documents=args.documents, trials=args.trials)
    serialized = json.dumps(result, indent=2) + "\n"
    if args.output:
        args.output.write_text(serialized, encoding="utf-8")
    print(serialized, end="")


if __name__ == "__main__":
    main()
