"""Exact search sessions and revision-pinned source retrieval."""
from __future__ import annotations

from uuid import UUID

from .errors import TribalError
from .storage import _uuid_bytes
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
