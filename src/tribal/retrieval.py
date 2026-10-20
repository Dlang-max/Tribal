"""Exact search sessions and revision-pinned source retrieval."""
from __future__ import annotations

import base64
from datetime import datetime, timezone
import json
import math
import struct
from uuid import UUID, uuid4

from .embeddings import _indexing_status, count_tokens, normalize_vector
from .errors import TribalError
from .storage import _row, _uuid_bytes
from .structure import parse_structure


def _one(connection, statement, parameters=()):
    with connection.cursor(dictionary=True) as cursor:
        cursor.execute(statement, parameters)
        return cursor.fetchone()


def _revision(connection, knowledge_base, document_id, revision_id=None):
    document = _uuid_bytes(document_id)
    revision = _uuid_bytes(revision_id) if revision_id is not None else None
    row = _one(
        connection,
        "SELECT r.*, dom.domain_key FROM documents d "
        "JOIN knowledge_bases kb ON kb.id=d.knowledge_base_id "
        "JOIN document_revisions r ON r.document_id=d.id "
        "AND r.knowledge_base_id=d.knowledge_base_id "
        "JOIN domains dom ON dom.id=r.domain_id "
        "WHERE kb.knowledge_base_key=%s AND d.id=%s AND r.id="
        + ("d.current_revision_id" if revision is None else "%s"),
        (knowledge_base, document) if revision is None else (knowledge_base, document, revision),
    )
    if row is None:
        raise TribalError(
            "E_NOT_FOUND", "Document revision does not belong to the requested document and knowledge base.",
            hint="Check the knowledge base, document ID, and revision ID.",
        )
    return row


def _parsed_revision(row):
    validation, structure = parse_structure(row["markdown"], path=row["vault_path"])
    if not validation["valid"] or structure is None:
        raise TribalError(
            "E_CHUNK_INVARIANT", "Stored revision cannot be parsed as valid canonical Markdown.",
            hint="Inspect the stored revision and restore its canonical source before reading context.",
        )
    return validation["document"], structure


def read_document(db, *, knowledge_base, document_id, revision_id=None,
                  start_byte=None, end_byte=None):
    """Read exact canonical source, including historical paths and revisions."""
    if (start_byte is None) != (end_byte is None):
        raise TribalError("E_ARGUMENT", "Source range endpoints must be supplied together.",
                          hint="Supply both start_byte and end_byte, or omit both.")
    with db.transaction(readonly=True) as connection:
        row = _revision(connection, knowledge_base, document_id, revision_id)
        document, _ = _parsed_revision(row)
        source = row["markdown"].encode("utf-8")
        start, end = (0, len(source)) if start_byte is None else (start_byte, end_byte)
        if (isinstance(start, bool) or isinstance(end, bool)
                or not isinstance(start, int) or not isinstance(end, int)
                or not 0 <= start <= end <= len(source)):
            raise TribalError("E_ARGUMENT", "Source range must be ordered byte offsets within the revision.",
                              expected={"minimum": 0, "maximum": len(source)},
                              hint="Use canonical UTF-8 byte offsets from a retrieved chunk.")
        try:
            # Validate each endpoint independently, including an empty range.
            source[:start].decode("utf-8")
            source[:end].decode("utf-8")
            content = source[start:end].decode("utf-8")
        except UnicodeDecodeError:
            raise TribalError("E_ARGUMENT", "Source range endpoints must lie on UTF-8 boundaries.",
                              hint="Use the start_byte and end_byte returned for a complete chunk.") from None
        return {
            "ok": True, "diagnostics": [], "document_id": document_id,
            "revision_id": str(UUID(bytes=bytes(row["id"]))),
            "path": row["vault_path"], "title": row["title"],
            "metadata": document["metadata"], "content_hash": bytes(row["content_hash"]).hex(),
            "start_byte": start, "end_byte": end, "content": content,
        }


def _all(connection, statement, parameters=()):
    with connection.cursor(dictionary=True) as cursor:
        cursor.execute(statement, parameters)
        return cursor.fetchall()


def _integer(value, field, minimum=0, maximum=None):
    if (isinstance(value, bool) or not isinstance(value, int) or value < minimum
            or (maximum is not None and value > maximum)):
        raise TribalError("E_ARGUMENT", f"{field} is outside its permitted integer range.",
                          field=field, expected={"minimum": minimum, "maximum": maximum},
                          hint="Supply an integer within the documented range.")


def _json(value):
    return json.loads(value) if isinstance(value, (str, bytes, bytearray)) else value


def _public(row):
    result = dict(row)
    for key, value in result.items():
        if isinstance(value, (bytes, bytearray)) and (key == "revision_id" or key == "document_id"):
            result[key] = str(UUID(bytes=bytes(value)))
        elif isinstance(value, datetime):
            result[key] = value.replace(tzinfo=timezone.utc).isoformat().replace("+00:00", "Z")
        elif key in ("heading_path", "scope", "contexts", "details"):
            result[key] = _json(value)
    return result


def _chunk(row, source=None):
    result = _public(row)
    if source is not None:
        start, end = result["start_byte"], result["end_byte"]
        if (not 0 <= start < end <= len(source)
                or source[start:end] != result["content"].encode("utf-8")):
            raise TribalError("E_CHUNK_INVARIANT", "Stored chunk differs from its canonical source range.",
                              hint="Rechunk the affected revision before retrieving its context.")
    return result


def read_context(db, *, knowledge_base, document_id, revision_id, chunk_id,
                 budget_bytes=65536):
    """Select whole same-section chunks, with diagrams before neighboring prose."""
    _integer(chunk_id, "chunk_id", 1)
    _integer(budget_bytes, "budget_bytes")
    with db.transaction(readonly=True) as connection:
        row = _revision(connection, knowledge_base, document_id, revision_id)
        _, structure = _parsed_revision(row)
        chunks = [_chunk(chunk, structure.canonical_bytes) for chunk in _all(
            connection, "SELECT * FROM document_chunks WHERE revision_id=%s ORDER BY ordinal",
            (_uuid_bytes(revision_id),))]
        matched = next((chunk for chunk in chunks if chunk["id"] == chunk_id), None)
        if matched is None:
            raise TribalError("E_NOT_FOUND", "Chunk does not belong to the requested revision.",
                              hint="Use a chunk ID returned for this document revision.")
        section = structure.section_for_range(matched["start_byte"], matched["end_byte"])
        if section is None:
            raise TribalError("E_CHUNK_INVARIANT", "Matched chunk crosses a structural section boundary.",
                              hint="Rechunk this revision using the current frozen chunk policy.")
        used = matched["end_byte"] - matched["start_byte"]
        if used > budget_bytes:
            raise TribalError("E_CONTEXT_BUDGET_EXCEEDED", "Complete matched chunk exceeds the context budget.",
                              expected=budget_bytes, actual=used,
                              hint="Increase budget_bytes to include the complete matched chunk.")
        candidates = [chunk for chunk in chunks
                      if section.start_byte <= chunk["start_byte"] < chunk["end_byte"] <= section.end_byte]
        def ordering(chunk):
            diagram = any(chunk["start_byte"] < region.end_byte and region.start_byte < chunk["end_byte"]
                          for region in structure.mermaid_ranges)
            distance = max(0, chunk["start_byte"] - matched["end_byte"],
                           matched["start_byte"] - chunk["end_byte"])
            return (not diagram, distance, chunk["start_byte"])
        selected = {(matched["start_byte"], matched["end_byte"]): matched}
        for chunk in sorted(candidates, key=ordering):
            location = (chunk["start_byte"], chunk["end_byte"])
            size = chunk["end_byte"] - chunk["start_byte"]
            if location not in selected and used + size <= budget_bytes:
                selected[location] = chunk
                used += size
        omitted = [chunk for chunk in candidates
                   if (chunk["start_byte"], chunk["end_byte"]) not in selected]
        return {
            "ok": True, "diagnostics": [], "document_id": document_id, "revision_id": revision_id,
            "matched_chunk_id": chunk_id, "section_start_byte": section.start_byte,
            "section_end_byte": section.end_byte, "budget_bytes": budget_bytes, "used_bytes": used,
            "chunks": sorted(selected.values(), key=lambda chunk: chunk["start_byte"]),
            "omitted_chunk_ids": [chunk["id"] for chunk in omitted],
            "omitted_bytes": sum(chunk["end_byte"] - chunk["start_byte"] for chunk in omitted),
            "complete": not omitted,
        }


def _knowledge_base(connection, key):
    row = _one(connection, "SELECT * FROM knowledge_bases WHERE knowledge_base_key=%s", (key,))
    if row is None:
        raise TribalError("E_NOT_FOUND", "Knowledge base is not registered.",
                          hint="Register the knowledge base before searching it.")
    return row


def _generations(row):
    return (row["knowledge_generation"], row["indexing_generation"], row["active_profile_id"])


def _indexing(connection, kb):
    normalized = _row(kb)
    if normalized["active_profile_id"] is not None:
        return _indexing_status(connection, normalized, normalized["active_profile_id"])
    # Lexical search works before profile activation. Without a profile there
    # are no compatible vector/job identities, so every current chunk is pending.
    total = _one(connection, "SELECT COUNT(*) AS total FROM documents d "
                 "JOIN document_chunks c ON c.revision_id=d.current_revision_id "
                 "WHERE d.knowledge_base_id=%s AND d.deleted_at IS NULL", (kb["id"],))["total"]
    return {
        "ok": True, "diagnostics": [], "knowledge_base_id": normalized["id"], "profile_id": None,
        "total": total, "embedded": 0, "pending": total, "oversized": 0, "failed": 0,
        "ready": total == 0, "knowledge_generation": kb["knowledge_generation"],
        "indexing_generation": kb["indexing_generation"],
    }


def _filters(value, field, allowed=None):
    if value is None:
        return None
    if not isinstance(value, (list, tuple)) or any(not isinstance(item, str) for item in value):
        raise TribalError("E_ARGUMENT", f"{field} must be a list of strings.", field=field,
                          hint="Supply registered domain keys or supported lifecycle statuses.")
    if allowed is not None and any(item not in allowed for item in value):
        raise TribalError("E_ARGUMENT", "Unsupported lifecycle status.", field=field,
                          expected=sorted(allowed), hint="Use active, superseded, or archived.")
    return sorted(set(value))


def _cursor(session_id, rank):
    payload = json.dumps([session_id, rank], separators=(",", ":")).encode("utf-8")
    return base64.urlsafe_b64encode(payload).decode("ascii").rstrip("=")


def _decode_cursor(value):
    try:
        if not isinstance(value, str) or not value or len(value) > 256:
            raise ValueError
        payload = base64.b64decode(value + "=" * (-len(value) % 4), altchars=b"-_", validate=True)
        session_id, rank = json.loads(payload)
        identity = _uuid_bytes(session_id)
        if isinstance(rank, bool) or not isinstance(rank, int) or rank < 2:
            raise ValueError
        return identity, rank
    except (ValueError, TypeError, UnicodeDecodeError, TribalError):
        raise TribalError("E_CURSOR_INVALID", "Search cursor is malformed.",
                          hint="Start a new search and use its returned next_cursor.") from None


def _expired():
    return TribalError("E_CURSOR_EXPIRED", "Search session expired or its knowledge base changed.",
                       hint="Start a new search to retrieve a current ranking.")


def _vector(value, dimensions):
    try:
        if isinstance(value, (bytes, bytearray, memoryview)):
            values = struct.unpack("<" + "f" * dimensions, value)
        else:
            values = tuple(float(component) for component in value)
        if len(values) != dimensions or not all(math.isfinite(component) for component in values):
            raise ValueError
        norm = math.hypot(*values)
        if not math.isfinite(norm) or norm == 0:
            raise ValueError
        return values, norm
    except (ValueError, TypeError, OverflowError, struct.error):
        raise TribalError("E_EMBEDDING_VECTOR", "Persisted embedding is not a finite nonzero profile vector.",
                          hint="Repair the affected profile embeddings before semantic search.") from None


def _rank(candidates, mode, lexical_mode):
    tie = lambda candidate: (candidate["document_id"], candidate["ordinal"])
    semantic = sorted((candidate for candidate in candidates if candidate["semantic_score"] is not None),
                      key=lambda candidate: (-candidate["semantic_score"], *tie(candidate)))
    lexical = []
    if mode != "semantic":
        field = "fulltext_score" if lexical_mode == "fulltext" else "literal_score"
        lexical = [candidate for candidate in candidates if candidate[field] > 0]
        if not lexical and lexical_mode == "fulltext":
            lexical_mode, field = "literal", "literal_score"
            lexical = [candidate for candidate in candidates if candidate[field] > 0]
        for candidate in lexical:
            candidate["lexical_score"] = candidate[field]
        lexical.sort(key=lambda candidate: (-candidate["lexical_score"], *tie(candidate)))
    if mode == "semantic":
        ranking = semantic
        for candidate in ranking:
            candidate["score"] = candidate["semantic_score"]
    elif mode == "lexical":
        ranking = lexical
        for candidate in ranking:
            candidate["score"] = candidate["lexical_score"]
    else:
        combined = {}
        for ordered in (semantic, lexical):
            for rank, candidate in enumerate(ordered, 1):
                entry = combined.setdefault(candidate["chunk_id"], candidate)
                entry["score"] = entry.get("score", 0.0) + 1.0 / (60 + rank)
        ranking = sorted(combined.values(), key=lambda candidate: (-candidate["score"], *tie(candidate)))
    return ranking, lexical_mode


def _scan(connection, kb, parameters, query_vector, dimensions, max_candidates):
    conditions = ["d.knowledge_base_id=%s"]
    bindings = [kb["id"]]
    if not parameters["include_deleted"]:
        conditions.append("d.deleted_at IS NULL")
    for field, column in (("domains", "dom.domain_key"), ("statuses", "r.status")):
        values = parameters[field]
        if values is not None:
            conditions.append(column + " IN (" + ",".join(["%s"] * len(values)) + ")" if values else "FALSE")
            bindings.extend(values)
    if parameters["domains"]:
        registered = {row["domain_key"] for row in _all(
            connection, "SELECT domain_key FROM domains WHERE knowledge_base_id=%s", (kb["id"],))}
        if set(parameters["domains"]) - registered:
            raise TribalError("E_NOT_FOUND", "Search domain is not registered in this knowledge base.",
                              hint="Use domain keys registered in the requested knowledge base.")
    tables = (" FROM documents d JOIN document_revisions r ON r.id=d.current_revision_id "
              "AND r.document_id=d.id JOIN domains dom ON dom.id=r.domain_id "
              "JOIN document_chunks c ON c.revision_id=r.id ")
    where = " WHERE " + " AND ".join(conditions)
    count = _one(connection, "SELECT COUNT(*) AS total" + tables + where, tuple(bindings))["total"]
    if count > max_candidates:
        raise TribalError("E_SEARCH_CAPACITY", "Eligible corpus exceeds the complete-search capacity.",
                          expected=max_candidates, actual=count,
                          hint="Narrow domains or statuses, or increase max_candidates after measuring capacity.")
    fulltext = parameters["mode"] != "semantic" and parameters["lexical_mode"] == "fulltext"
    columns = ("SELECT d.id AS document_id,r.id AS revision_id,c.id AS chunk_id,c.ordinal,"
               "r.title,r.summary,c.content,CAST(ce.embedding AS BINARY) AS embedding,")
    columns += ("MATCH(r.title,r.summary) AGAINST(%s IN NATURAL LANGUAGE MODE) + "
                "MATCH(c.content) AGAINST(%s IN NATURAL LANGUAGE MODE) AS fulltext_score"
                if fulltext else "0 AS fulltext_score")
    statement = (columns + tables + "LEFT JOIN chunk_embeddings ce ON ce.chunk_id=c.id AND ce.profile_id=%s"
                 + where)
    values = ([parameters["query"], parameters["query"]] if fulltext else [])
    values.extend([kb["active_profile_id"], *bindings])
    query_values, query_norm = _vector(query_vector, dimensions) if query_vector is not None else (None, None)
    candidates = []
    with connection.cursor(dictionary=True) as cursor:
        cursor.execute(statement, tuple(values))
        try:
            for row in cursor:
                semantic_score = None
                if query_values is not None and row["embedding"] is not None:
                    vector, norm = _vector(row["embedding"], dimensions)
                    semantic_score = math.fsum(a * b for a, b in zip(query_values, vector)) / (query_norm * norm)
                candidates.append({
                    "document_id": bytes(row["document_id"]), "revision_id": bytes(row["revision_id"]),
                    "chunk_id": row["chunk_id"], "ordinal": row["ordinal"],
                    "semantic_score": semantic_score, "lexical_score": None,
                    "fulltext_score": float(row["fulltext_score"]),
                    "literal_score": float(sum(parameters["query"] in row[field]
                                               for field in ("title", "summary", "content"))),
                })
        finally:
            # Drain on operational scoring failure before closing the streaming cursor.
            if connection.unread_result:
                for _ in cursor:
                    pass
    return _rank(candidates, parameters["mode"], parameters["lexical_mode"])


def _page(connection, kb, session, next_rank, limit, parameters):
    if session["knowledge_base_id"] != kb["id"] or _json(session["parameters"]) != parameters:
        raise TribalError("E_CURSOR_INVALID", "Search parameters differ from the stored session.",
                          hint="Repeat the original query, mode, and filters or start a new search.")
    if (session["knowledge_generation"] != kb["knowledge_generation"]
            or session["indexing_generation"] != kb["indexing_generation"]
            or session["profile_id"] != kb["active_profile_id"] or session["expired"]):
        raise _expired()
    if next_rank > max(1, session["result_count"]):
        raise TribalError("E_CURSOR_INVALID", "Search cursor rank is outside its stored ranking.",
                          hint="Use the most recent next_cursor returned by this search.")
    rows = _all(connection, """
        SELECT sr.`rank`,sr.score,sr.semantic_score,sr.lexical_score,sr.document_id,sr.revision_id,
               c.id AS chunk_id,c.ordinal,r.vault_path AS path,r.title,r.summary,dom.domain_key AS domain,
               c.heading_path,c.section_anchor,c.start_byte,c.end_byte,c.content,
               r.verification_state,r.verified_at,r.scope,r.contexts
        FROM search_session_results sr JOIN document_chunks c ON c.id=sr.chunk_id AND c.revision_id=sr.revision_id
        JOIN document_revisions r ON r.id=sr.revision_id AND r.document_id=sr.document_id
        JOIN domains dom ON dom.id=r.domain_id
        WHERE sr.session_id=%s AND sr.`rank` >= %s ORDER BY sr.`rank` LIMIT %s
        """, (session["id"], next_rank, limit))
    expected = min(limit, max(0, session["result_count"] - next_rank + 1))
    if len(rows) != expected:
        raise _expired()
    source_cache = {}
    hits = []
    for row in rows:
        revision = bytes(row["revision_id"])
        if revision not in source_cache:
            source_cache[revision] = [_public(source) for source in _all(
                connection, "SELECT * FROM document_sources WHERE revision_id=%s ORDER BY id", (revision,))]
        hit = _public(row)
        hit["sources"] = source_cache[revision]
        hit["applicability"] = "unknown"
        hits.append(hit)
    following = next_rank + len(hits)
    return {
        "ok": True, "diagnostics": [], "query": session["query"], "mode": session["mode"],
        "lexical_mode": session["lexical_mode"],
        "profile_id": str(UUID(bytes=bytes(session["profile_id"]))) if session["profile_id"] else None,
        "knowledge_generation": kb["knowledge_generation"], "indexing_generation": kb["indexing_generation"],
        "indexing": _indexing(connection, kb), "hits": hits,
        "next_cursor": _cursor(str(UUID(bytes=bytes(session["id"]))), following)
                       if following <= session["result_count"] else None,
        "expires_at": session["expires_at"].replace(tzinfo=timezone.utc).isoformat().replace("+00:00", "Z"),
    }


def _session(connection, identity):
    return _one(connection, "SELECT *,CURRENT_TIMESTAMP(6)>=expires_at AS expired FROM search_sessions WHERE id=%s",
                (identity,))


def search(db, query: str, *, knowledge_base, provider=None, mode="semantic", lexical_mode="fulltext",
           domains=None, statuses=None, include_deleted=False, limit=20, cursor=None,
           max_candidates=100000):
    """Rank the full eligible corpus and materialize an expiring stable session."""
    _integer(limit, "limit", 1, 100)
    _integer(max_candidates, "max_candidates", 1)
    if not isinstance(query, str) or not query.strip():
        raise TribalError("E_ARGUMENT", "Search query must contain non-whitespace text.",
                          hint="Supply the complete query text to search.")
    if mode not in ("semantic", "lexical", "hybrid") or lexical_mode not in ("fulltext", "literal"):
        raise TribalError("E_ARGUMENT", "Unsupported search or lexical mode.",
                          hint="Use semantic, lexical, or hybrid with fulltext or literal lexical ranking.")
    if not isinstance(include_deleted, bool):
        raise TribalError("E_ARGUMENT", "include_deleted must be a boolean.")
    parameters = {"query": query, "mode": mode, "lexical_mode": lexical_mode,
                  "domains": _filters(domains, "domains"),
                  "statuses": ["active"] if statuses is None else _filters(
                      statuses, "statuses", {"active", "superseded", "archived"}),
                  "include_deleted": include_deleted}
    if cursor is not None:
        identity, next_rank = _decode_cursor(cursor)
        with db.transaction(readonly=True) as connection:
            kb = _knowledge_base(connection, knowledge_base)
            session = _session(connection, identity)
            if session is None:
                raise TribalError("E_CURSOR_INVALID", "Search session does not exist.",
                                  hint="Start a new search and use its returned cursor.")
            return _page(connection, kb, session, next_rank, limit, parameters)
    query_vector = None
    dimensions = None
    with db.transaction(readonly=True) as connection:
        initial_kb = _knowledge_base(connection, knowledge_base)
        profile = _one(connection, "SELECT * FROM embedding_profiles WHERE id=%s",
                       (initial_kb["active_profile_id"],)) if initial_kb["active_profile_id"] else None
    if mode != "lexical":
        if profile is None:
            raise TribalError("E_NOT_FOUND", "Knowledge base has no active embedding profile.",
                              hint="Activate a compatible embedding profile before semantic search.")
        if provider is None:
            raise TribalError("E_ARGUMENT", "Semantic and hybrid search require an embedding provider.",
                              hint="Pass a provider compatible with the active profile.")
        configuration = _json(profile["configuration"])
        if count_tokens(query, encoding=configuration["encoding"]) > configuration["max_input_tokens"]:
            raise TribalError("E_ARGUMENT", "Query exceeds the active embedding profile input limit.",
                              hint="Shorten the query without changing the stored document chunks.")
        dimensions = profile["dimensions"]
        try:
            values = provider.embed(query, model=profile["model"], dimensions=dimensions)
        except Exception:
            raise TribalError("E_EMBEDDING_PROVIDER", "Query embedding provider failed.",
                              hint="Check provider availability and retry the search.") from None
        query_vector = normalize_vector(values, dimensions=dimensions)
    with db.transaction(readonly=True) as connection:
        kb = _knowledge_base(connection, knowledge_base)
        if kb["active_profile_id"] != initial_kb["active_profile_id"]:
            raise _expired()
        ranking, actual_lexical = _scan(connection, kb, parameters, query_vector, dimensions, max_candidates)
    # Scoring is outside the publication lock. Recheck the exact snapshot before
    # publishing its ranking; a racing mutation yields no session or partial page.
    with db.transaction() as connection:
        current = _one(connection, "SELECT * FROM knowledge_bases WHERE knowledge_base_key=%s FOR UPDATE",
                       (knowledge_base,))
        if current is None or _generations(current) != _generations(kb):
            raise _expired()
        identity = uuid4().bytes
        with connection.cursor() as sql:
            sql.execute("""
                INSERT INTO search_sessions
                (id,knowledge_base_id,profile_id,query,query_vector,mode,lexical_mode,parameters,
                 knowledge_generation,indexing_generation,result_count,expires_at)
                VALUES (%s,%s,%s,%s,STRING_TO_VECTOR(%s),%s,%s,%s,%s,%s,%s,
                        DATE_ADD(CURRENT_TIMESTAMP(6),INTERVAL 15 MINUTE))
                """, (identity, kb["id"], kb["active_profile_id"], query,
                      json.dumps(query_vector) if query_vector is not None else None, mode, actual_lexical,
                      json.dumps(parameters, ensure_ascii=False, separators=(",", ":")),
                      kb["knowledge_generation"], kb["indexing_generation"], len(ranking)))
            for offset in range(0, len(ranking), 1000):
                sql.executemany("""
                    INSERT INTO search_session_results
                    (session_id,`rank`,document_id,revision_id,chunk_id,score,semantic_score,lexical_score)
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
                    """, [(identity, rank, candidate["document_id"], candidate["revision_id"],
                           candidate["chunk_id"], candidate["score"], candidate["semantic_score"],
                           candidate["lexical_score"])
                          for rank, candidate in enumerate(ranking[offset:offset+1000], offset+1)])
        return _page(connection, current, _session(connection, identity), 1, limit, parameters)
