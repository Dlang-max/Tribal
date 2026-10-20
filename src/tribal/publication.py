"""Atomic publication of authored revisions and derived chunk sets."""
from __future__ import annotations

from datetime import datetime
import json
from uuid import UUID, uuid4

from .chunking import chunk_document
from . import embeddings
from .errors import TribalError
from .parser import _portable, validate_vault
from .storage import _uuid_bytes, advance_generations, lock_knowledge_base


def _rows(connection, statement, parameters=()):
    with connection.cursor(dictionary=True) as cursor:
        cursor.execute(statement, parameters)
        return cursor.fetchall()


def _write(connection, statement, parameters=()):
    with connection.cursor() as cursor:
        cursor.execute(statement, parameters)
        return cursor.lastrowid


def _identity(value):
    return str(UUID(bytes=bytes(value))) if value is not None else None


def _json(value):
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), allow_nan=False)


def _heads(connection, kb_id, submitted_ids=()):
    """Current reads include deleted reservations; lock documents in UUID order."""
    parameters = [_uuid_bytes(kb_id)]
    selection = "d.knowledge_base_id=%s"
    if submitted_ids:
        selection += " OR d.id IN (" + ",".join(["%s"] * len(submitted_ids)) + ")"
        parameters.extend(_uuid_bytes(value) for value in sorted(submitted_ids))
    rows = _rows(connection,
        "SELECT d.*,r.markdown,r.content_hash,r.revision_number,r.title "
        "FROM documents d LEFT JOIN document_revisions r ON r.id=d.current_revision_id "
        f"WHERE {selection} ORDER BY d.id FOR UPDATE", tuple(parameters))
    result = {}
    for row in rows:
        if _identity(row["knowledge_base_id"]) != kb_id:
            raise TribalError("E_ASSIGNMENT", "Document identity belongs to another knowledge base.",
                              actual=_identity(row["id"]),
                              hint="Use the document's registered knowledge base or a new identity.")
        if row["current_revision_id"] is None:
            raise TribalError("E_DATABASE", "Stored document has no current revision.",
                              hint="Restore a complete database backup before publication.")
        result[_identity(row["id"])] = row
    return result


def _domains(connection, kb_id):
    return {row["domain_key"]: row["id"] for row in _rows(connection,
        "SELECT id,domain_key FROM domains WHERE knowledge_base_id=%s FOR UPDATE",
        (_uuid_bytes(kb_id),))}


def _check_paths(heads, submitted):
    """Check final paths, retaining every soft-deleted document's reservation."""
    paths = {identity: row["vault_path"] for identity, row in heads.items()}
    paths.update({document["metadata"]["id"]: path for path, document in submitted.items()})
    occupied = {}
    for identity, path in paths.items():
        portable = _portable(path)
        if portable in occupied:
            other = occupied[portable]
            raise TribalError("E_PATH", "Final path conflicts with a reserved document path.",
                              path=path, field="path", actual=path, expected="a portable unique path",
                              hint=f"Choose a path distinct from {other!r}, including case and Unicode folding.")
        occupied[portable] = path


def _validate_namespace(heads, submitted, originals, *, knowledge_base, domains):
    replaced = {document["metadata"]["id"] for document in submitted.values()}
    namespace = {row["vault_path"]: row["markdown"] for identity, row in heads.items()
                 if identity not in replaced and row["deleted_at"] is None}
    namespace.update(originals)
    return validate_vault(namespace, knowledge_base=knowledge_base, domains=domains)


def _failure(validation):
    return {"ok": False, "diagnostics": validation["diagnostics"], "validation": validation}


def _generations(kb, *, knowledge=False, indexing=False):
    return {"knowledge_generation": kb["knowledge_generation"] + int(knowledge),
            "indexing_generation": kb["indexing_generation"] + int(indexing)}


def _chunks(connection, revision_id):
    return _rows(connection,
        "SELECT id,chunker_version FROM document_chunks WHERE revision_id=%s ORDER BY ordinal FOR UPDATE",
        (_uuid_bytes(revision_id),))


def _insert_chunks(connection, revision_id, chunks):
    stored = []
    for chunk in chunks:
        identity = _write(connection,
            "INSERT INTO document_chunks "
            "(revision_id,ordinal,heading_path,section_anchor,content,start_byte,end_byte,chunker_version) "
            "VALUES (%s,%s,%s,%s,%s,%s,%s,%s)",
            (_uuid_bytes(revision_id), chunk["ordinal"], _json(chunk["heading_path"]),
             chunk["section_anchor"], chunk["content"], chunk["start_byte"], chunk["end_byte"],
             chunk["chunker_version"]))
        stored.append({**chunk, "id": identity, "revision_id": revision_id})
    return stored


def _insert_revision(connection, *, kb_id, domain_id, document, path, revision_id,
                     previous, author_type, author_id, change_summary):
    metadata = document["metadata"]
    verified_at = metadata.get("verified_at")
    if verified_at is not None:
        verified_at = datetime.strptime(verified_at, "%Y-%m-%dT%H:%M:%SZ")
    _write(connection,
        "INSERT INTO document_revisions "
        "(id,document_id,knowledge_base_id,domain_id,revision_number,parent_revision_id,"
        "schema_version,vault_path,title,summary,kind,status,verification_state,verified_at,"
        "scope,contexts,tags,aliases,markdown,content_hash,author_type,author_id,change_summary) "
        "VALUES (" + ",".join(["%s"] * 23) + ")",
        (_uuid_bytes(revision_id), _uuid_bytes(metadata["id"]), _uuid_bytes(kb_id), domain_id,
         previous["revision_number"] + 1 if previous else 1,
         previous["current_revision_id"] if previous else None, metadata["schema_version"],
         path, metadata["title"], metadata["summary"], metadata["kind"], metadata["status"],
         metadata["verification_state"], verified_at, _json(metadata["scope"]),
         _json(metadata["contexts"]), _json(metadata["tags"]), _json(metadata["aliases"]),
         document["canonical_markdown"], bytes.fromhex(document["content_hash"]),
         author_type, author_id, change_summary))
    for source in metadata["sources"]:
        _write(connection,
            "INSERT INTO document_sources "
            "(revision_id,section_anchor,source_type,locator,context_key,source_revision,details) "
            "VALUES (%s,%s,%s,%s,%s,%s,%s)",
            (_uuid_bytes(revision_id), source.get("section"), source["type"], source["locator"],
             source.get("context"), source.get("revision"),
             _json(source["details"]) if "details" in source else None))


def _refresh_links(connection, validation, revision_ids, new_revisions=()):
    """Only current occurrences change; noncurrent bindings retain their history."""
    for result in validation["documents"].values():
        document = result["document"]
        revision_id = revision_ids[document["metadata"]["id"]]
        for link in document["links"]:
            target = _uuid_bytes(link["target_document_id"]) if link["target_document_id"] else None
            if revision_id in new_revisions:
                _write(connection,
                    "INSERT INTO document_links "
                    "(source_revision_id,ordinal,source_anchor,raw_link,target_text,target_anchor,target_document_id) "
                    "VALUES (%s,%s,%s,%s,%s,%s,%s)",
                    (_uuid_bytes(revision_id), link["ordinal"], link["source_anchor"], link["raw_link"],
                     link["target_text"], link["target_anchor"], target))
            else:
                _write(connection,
                    "UPDATE document_links SET target_document_id=%s "
                    "WHERE source_revision_id=%s AND ordinal=%s",
                    (target, _uuid_bytes(revision_id), link["ordinal"]))


def ingest_vault(db, documents, *, knowledge_base, author_type="human", author_id="cli",
                 change_summary=None):
    """Publish a batch against the complete KB namespace, without implicit deletion."""
    if author_type not in ("human", "agent", "system"):
        raise TribalError("E_ARGUMENT", "Author type must be human, agent, or system.")
    if not isinstance(author_id, str) or not author_id.strip() or len(author_id) > 255:
        raise TribalError("E_ARGUMENT", "Author ID must contain 1..255 characters.")
    if change_summary is not None and not isinstance(change_summary, str):
        raise TribalError("E_ARGUMENT", "Change summary must be text or null.")
    preliminary = validate_vault(documents, knowledge_base=knowledge_base)
    if not preliminary["valid"]:
        return _failure(preliminary)
    submitted = {path: result["document"] for path, result in preliminary["documents"].items()}
    layouts = {path: chunk_document(content, path=path, knowledge_base=knowledge_base)
               for path, content in documents.items()}
    for path, layout in layouts.items():
        if (not layout["valid"] or layout["content_hash"] != submitted[path]["content_hash"]
                or layout["document_id"] != submitted[path]["metadata"]["id"]):
            raise TribalError("E_CHUNK_INVARIANT", "Chunk layout does not match the validated source.",
                              path=path, hint="Inspect the chunker before retrying publication.")
    with db.transaction() as connection:
        kb = lock_knowledge_base(connection, knowledge_base)
        heads = _heads(connection, kb["id"], [doc["metadata"]["id"] for doc in submitted.values()])
        domains = _domains(connection, kb["id"])
        actions = {}
        for path, document in submitted.items():
            previous = heads.get(document["metadata"]["id"])
            if previous is not None and previous["deleted_at"] is not None:
                raise TribalError("E_DELETED", "Ordinary ingestion cannot restore a deleted document.",
                                  path=path, hint="Restore the document explicitly using its current revision.")
            unchanged = previous is not None and previous["vault_path"] == path and bytes(previous["content_hash"]).hex() == document["content_hash"]
            actions[path] = "unchanged" if unchanged else "updated" if previous else "created"
            if previous is not None and not unchanged:
                base = document["base_revision"]
                if base is None:
                    raise TribalError("E_BASE_REVISION_REQUIRED", "Changed document requires its current base revision.",
                                      path=path, actual={"document_id": document["metadata"]["id"],
                                                        "revision_id": _identity(previous["current_revision_id"])},
                                      hint="Read the current document and include tribal_base_revision before editing.")
                if base != _identity(previous["current_revision_id"]):
                    raise TribalError("E_REVISION_CONFLICT", "Document changed since the submitted base revision.",
                                      path=path, expected=_identity(previous["current_revision_id"]), actual=base,
                                      hint="Read the current revision and reconcile the authored changes.")
        _check_paths(heads, submitted)
        validation = _validate_namespace(heads, submitted, documents,
                                         knowledge_base=knowledge_base, domains=domains)
        if not validation["valid"]:
            return _failure(validation)
        # Vacate all changed paths first so occupied-path swaps remain atomic.
        for path, document in submitted.items():
            identity = document["metadata"]["id"]
            previous = heads.get(identity)
            if previous and previous["vault_path"] != path:
                _write(connection, "UPDATE documents SET vault_path=%s WHERE id=%s",
                       (f".tribal-staging/{identity}.md", _uuid_bytes(identity)))
        revision_ids = {identity: _identity(row["current_revision_id"]) for identity, row in heads.items()}
        summary = dict(created=0, updated=0, unchanged=0, chunks=0, jobs=0)
        outcomes = {}
        new_revisions = set()
        diagnostics = list(validation["diagnostics"])
        for path, document in submitted.items():
            identity = document["metadata"]["id"]
            previous = heads.get(identity)
            action = actions[path]
            summary[action] += 1
            extra = [item for item in layouts[path]["diagnostics"] if item["code"] == "W_OVERSIZED_BLOCK"]
            outcome_diagnostics = list(validation["documents"][path]["diagnostics"]) + extra
            diagnostics.extend(extra)
            if action == "unchanged":
                revision_id = revision_ids[identity]
                chunk_ids = [row["id"] for row in _chunks(connection, revision_id)]
            else:
                revision_id = str(uuid4())
                if previous is None:
                    _write(connection,
                        "INSERT INTO documents (id,knowledge_base_id,vault_path) VALUES (%s,%s,%s)",
                        (_uuid_bytes(identity), _uuid_bytes(kb["id"]), path))
                _insert_revision(connection, kb_id=kb["id"], domain_id=domains[document["metadata"]["domain"]],
                                 document=document, path=path, revision_id=revision_id, previous=previous,
                                 author_type=author_type, author_id=author_id, change_summary=change_summary)
                stored = _insert_chunks(connection, revision_id, layouts[path]["chunks"])
                queued = embeddings.enqueue_chunks(connection, knowledge_base_id=kb["id"],
                                                    profile_id=kb["active_profile_id"], chunks=stored,
                                                    title=document["metadata"]["title"])
                diagnostics.extend(queued["diagnostics"])
                outcome_diagnostics.extend(queued["diagnostics"])
                chunk_ids = [chunk["id"] for chunk in stored]
                summary["chunks"] += len(stored)
                summary["jobs"] += queued["enqueued"]
                _write(connection, "UPDATE documents SET vault_path=%s,current_revision_id=%s WHERE id=%s",
                       (path, _uuid_bytes(revision_id), _uuid_bytes(identity)))
                revision_ids[identity] = revision_id
                new_revisions.add(revision_id)
            outcomes[path] = dict(document_id=identity, revision_id=revision_id,
                                  previous_revision_id=_identity(previous["current_revision_id"]) if previous else None,
                                  action=action, path=path, chunk_ids=chunk_ids, diagnostics=outcome_diagnostics)
        changed = bool(new_revisions)
        if changed:
            _refresh_links(connection, validation, revision_ids, new_revisions)
        advance_generations(connection, kb["id"], knowledge=changed, indexing=changed)
        return dict(ok=True, diagnostics=diagnostics, knowledge_base_id=kb["id"],
                    documents=outcomes, summary=summary, **_generations(kb, knowledge=changed, indexing=changed))


def set_document_deleted(db, *, knowledge_base, document_id, expected_revision, deleted=True):
    """Explicitly delete or restore a head, retaining authored and derived history."""
    _uuid_bytes(document_id)
    _uuid_bytes(expected_revision)
    if type(deleted) is not bool:
        raise TribalError("E_ARGUMENT", "Deleted must be a boolean.")
    with db.transaction() as connection:
        kb = lock_knowledge_base(connection, knowledge_base)
        heads = _heads(connection, kb["id"])
        document = heads.get(document_id)
        if document is None:
            raise TribalError("E_NOT_FOUND", "Document is not in the requested knowledge base.")
        revision_id = _identity(document["current_revision_id"])
        if revision_id != expected_revision:
            raise TribalError("E_REVISION_CONFLICT", "Document head differs from the expected revision.",
                              expected=revision_id, actual=expected_revision,
                              hint="Read the current head before changing its lifecycle.")
        changed = (document["deleted_at"] is not None) != deleted
        diagnostics = []
        if changed:
            document["deleted_at"] = True if deleted else None
            _check_paths(heads, {})
            validation = _validate_namespace(heads, {}, {}, knowledge_base=knowledge_base,
                                             domains=_domains(connection, kb["id"]))
            if not validation["valid"]:
                return _failure(validation)
            _write(connection, "UPDATE documents SET deleted_at=" + ("CURRENT_TIMESTAMP(6)" if deleted else "NULL") + " WHERE id=%s",
                   (_uuid_bytes(document_id),))
            revision_ids = {identity: _identity(row["current_revision_id"]) for identity, row in heads.items()}
            _refresh_links(connection, validation, revision_ids)
            diagnostics = validation["diagnostics"]
            advance_generations(connection, kb["id"], knowledge=True)
        return dict(ok=True, diagnostics=diagnostics, document_id=document_id, revision_id=revision_id,
                    deleted=deleted, changed=changed, **_generations(kb, knowledge=changed))


def rechunk_revision(db, *, knowledge_base, document_id, revision_id=None, expected_chunk_ids=None):
    """Replace one complete chunk set with fresh identities and durable jobs."""
    document_bytes = _uuid_bytes(document_id)
    if revision_id is not None:
        _uuid_bytes(revision_id)
    if expected_chunk_ids is not None and (not isinstance(expected_chunk_ids, list)
            or any(type(value) is not int or value <= 0 for value in expected_chunk_ids)):
        raise TribalError("E_ARGUMENT", "Expected chunk IDs must be an ordered list of positive integers.")
    with db.transaction(readonly=True) as connection:
        rows = _rows(connection,
            "SELECT r.* FROM documents d JOIN knowledge_bases k ON k.id=d.knowledge_base_id "
            "JOIN document_revisions r ON r.document_id=d.id AND r.id=" + ("%s " if revision_id else "d.current_revision_id ") +
            "WHERE d.id=%s AND k.knowledge_base_key=%s",
            ((_uuid_bytes(revision_id),) if revision_id else ()) + (document_bytes, knowledge_base))
        if not rows:
            raise TribalError("E_NOT_FOUND", "Requested document revision is unavailable.")
        revision = rows[0]
        captured_id = _identity(revision["id"])
        captured = _rows(connection,
            "SELECT id,chunker_version FROM document_chunks WHERE revision_id=%s ORDER BY ordinal",
            (revision["id"],))
    old_ids = [row["id"] for row in captured]
    if expected_chunk_ids is not None and old_ids != expected_chunk_ids:
        raise TribalError("E_CONFLICT", "Revision chunk set differs from the expected identities.",
                          hint="Reload the selected revision's chunks before rechunking.")
    layout = chunk_document(revision["markdown"], path=revision["vault_path"],
                            revision_id=captured_id, knowledge_base=knowledge_base)
    if (not layout["valid"] or layout["content_hash"] != bytes(revision["content_hash"]).hex()
            or layout["document_id"] != document_id):
        raise TribalError("E_CHUNK_INVARIANT", "Stored revision cannot be chunked as valid authored source.",
                          hint="Inspect the stored revision and restore valid source before retrying.")
    with db.transaction() as connection:
        kb = lock_knowledge_base(connection, knowledge_base)
        heads = _heads(connection, kb["id"])
        head = heads.get(document_id)
        if head is None or revision["knowledge_base_id"] != _uuid_bytes(kb["id"]):
            raise TribalError("E_NOT_FOUND", "Requested document revision is unavailable.")
        if revision_id is None and _identity(head["current_revision_id"]) != captured_id:
            raise TribalError("E_CONFLICT", "Current revision changed during rechunking.",
                              hint="Recompute the replacement for the current revision.")
        current = _chunks(connection, captured_id)
        if current != captured:
            raise TribalError("E_CONFLICT", "Revision chunk set changed during rechunking.",
                              hint="Reload the complete chunk set and retry.")
        _write(connection,
            "DELETE e FROM chunk_embeddings e JOIN document_chunks c ON c.id=e.chunk_id WHERE c.revision_id=%s",
            (revision["id"],))
        _write(connection,
            "UPDATE embedding_jobs j JOIN document_chunks c ON c.id=j.chunk_id "
            "SET j.state='discarded',j.claim_token=NULL,j.lease_expires_at=NULL,j.updated_at=CURRENT_TIMESTAMP(6) "
            "WHERE c.revision_id=%s", (revision["id"],))
        _write(connection, "DELETE FROM document_chunks WHERE revision_id=%s", (revision["id"],))
        stored = _insert_chunks(connection, captured_id, layout["chunks"])
        queued = embeddings.enqueue_chunks(connection, knowledge_base_id=kb["id"],
                                            profile_id=kb["active_profile_id"], chunks=stored, title=revision["title"])
        advance_generations(connection, kb["id"], indexing=True)
        return dict(ok=True, diagnostics=layout["diagnostics"] + queued["diagnostics"],
                    document_id=document_id, revision_id=captured_id, old_chunk_ids=old_ids,
                    chunk_ids=[chunk["id"] for chunk in stored], jobs=queued["enqueued"],
                    **_generations(kb, indexing=True))
