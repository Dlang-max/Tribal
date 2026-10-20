"""Exact embedding inputs, providers, and durable fenced indexing operations."""
from __future__ import annotations

from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
import hashlib
import json
import math
import struct
from uuid import UUID, uuid4

from .errors import TribalError
from .storage import _one, _row, _uuid_bytes, advance_generations, lock_knowledge_base


def format_document_input(title: str, heading_path: list[str], content: str) -> str:
    """Format tribal-title-headings-v1 without modifying the source passage."""
    headings = json.dumps(heading_path, ensure_ascii=False, separators=(",", ":"))
    return "Title: " + title + "\nHeadings: " + headings + "\n\n" + content


def input_hash(text: str) -> str:
    """Hash the complete, exact UTF-8 input submitted to a provider."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def count_tokens(text: str, *, encoding="cl100k_base") -> int:
    import tiktoken

    return len(tiktoken.get_encoding(encoding).encode(text, disallowed_special=()))


def normalize_vector(values, *, dimensions: int) -> list[float]:
    """Validate, L2 normalize in float64, and return exact float32 components."""
    def invalid():
        return TribalError(
            "E_EMBEDDING_VECTOR", "Embedding must be a finite, nonzero vector of the profile dimensions.",
            expected=dimensions, hint="Check the provider model and profile dimensions.",
        )

    if isinstance(dimensions, bool) or not isinstance(dimensions, int) or not 1 <= dimensions <= 16383:
        raise invalid()
    try:
        vector = [float(value) for value in values]
    except (TypeError, ValueError, OverflowError) as exc:
        raise invalid() from exc
    if len(vector) != dimensions or not all(math.isfinite(value) for value in vector):
        raise invalid()
    scale = max(abs(value) for value in vector)
    if scale == 0:
        raise invalid()
    scaled = [value / scale for value in vector]
    norm = math.hypot(*scaled)
    try:
        packed = struct.pack("<" + "f" * dimensions, *(value / norm for value in scaled))
        result = list(struct.unpack("<" + "f" * dimensions, packed))
    except (OverflowError, struct.error) as exc:
        raise invalid() from exc
    if not all(math.isfinite(value) for value in result) or math.hypot(*result) == 0:
        raise invalid()
    return result


class DeterministicProvider:
    """Stable offline vectors for exercising the complete indexing pipeline.

    These vectors reproduce provider behavior without credentials; they do not
    claim semantic quality. Model identity and dimensionality seed the output.
    """

    def embed(self, text: str, *, model: str, dimensions: int) -> list[float]:
        if isinstance(dimensions, bool) or not isinstance(dimensions, int) or not 1 <= dimensions <= 16383:
            raise TribalError("E_ARGUMENT", "Embedding dimensions must be between 1 and 16383.")
        seed = json.dumps([model, dimensions, text], ensure_ascii=False, separators=(",", ":"))
        values = struct.unpack("<" + "I" * dimensions, hashlib.shake_256(seed.encode("utf-8")).digest(4 * dimensions))
        return normalize_vector([value / 2147483648.0 - 1.0 for value in values], dimensions=dimensions)


class _ProviderFailure(TribalError):
    """Safe provider failure plus private durable-retry metadata."""

    def __init__(self, *, transient=False, oversized=False, retry_after=None):
        super().__init__(
            "E_EMBEDDING_PROVIDER", "Embedding provider request failed.",
            hint="Check provider availability, credentials, and profile configuration; retry failed indexing work.",
        )
        self.transient = transient
        self.oversized = oversized
        self.retry_after = retry_after


def _retry_after(headers):
    """Return an explicit provider delay, including HTTP-date guidance."""
    value = headers.get("retry-after-ms")
    if value is not None:
        try:
            seconds = float(value) / 1000
            if math.isfinite(seconds) and seconds >= 0:
                return seconds
        except (ValueError, TypeError):
            pass
    value = headers.get("retry-after")
    if value is None:
        return None
    try:
        seconds = float(value)
    except (TypeError, ValueError):
        try:
            retry_at = parsedate_to_datetime(value)
            if retry_at.tzinfo is None:
                retry_at = retry_at.replace(tzinfo=timezone.utc)
            seconds = (retry_at - datetime.now(timezone.utc)).total_seconds()
        except (ValueError, TypeError, OverflowError):
            return None
    return max(0.0, seconds) if math.isfinite(seconds) else None


class OpenAIProvider:
    """OpenAI adapter; the durable worker, rather than the SDK, owns retries."""

    def __init__(self, *, api_key=None):
        import openai

        try:
            self.client = openai.OpenAI(api_key=api_key, timeout=30.0, max_retries=0)
        except openai.OpenAIError as exc:
            raise _ProviderFailure() from exc

    def embed(self, text: str, *, model: str, dimensions: int) -> list[float]:
        import openai

        try:
            response = self.client.embeddings.create(
                model=model, input=text, dimensions=dimensions, encoding_format="float",
            )
        except openai.APIConnectionError as exc:
            raise _ProviderFailure(transient=True) from exc
        except openai.APIStatusError as exc:
            status = exc.status_code
            body = exc.body if isinstance(exc.body, dict) else {}
            error = body.get("error", body)
            oversized = isinstance(error, dict) and error.get("code") == "context_length_exceeded"
            raise _ProviderFailure(
                transient=status in (408, 409, 429) or status >= 500,
                oversized=oversized, retry_after=_retry_after(exc.response.headers),
            ) from exc
        except openai.OpenAIError as exc:
            raise _ProviderFailure() from exc
        if len(response.data) != 1:
            raise TribalError("E_EMBEDDING_VECTOR", "Provider did not return exactly one embedding.")
        return list(response.data[0].embedding)


def enqueue_chunks(connection, *, knowledge_base_id, profile_id, chunks, title):
    """Enqueue exact stored chunk identities in the caller's KB transaction.

    The caller holds the knowledge-base lock and owns generation advancement.
    Token classification and compatible-vector reuse happen in the worker.
    """
    result = {"enqueued": 0, "reused": 0, "diagnostics": []}
    if profile_id is None:
        return result
    kb_id = _uuid_bytes(knowledge_base_id)
    selected_profile = _uuid_bytes(profile_id)
    if _one(connection, "SELECT id FROM embedding_profiles WHERE id=%s", (selected_profile,)) is None:
        raise TribalError("E_NOT_FOUND", "Embedding profile is not registered.")
    for chunk in chunks:
        revision_id = _uuid_bytes(chunk["revision_id"])
        stored = _one(
            connection,
            "SELECT c.id FROM document_chunks c JOIN document_revisions r ON r.id=c.revision_id "
            "WHERE c.id=%s AND c.revision_id=%s AND r.knowledge_base_id=%s",
            (chunk["id"], revision_id, kb_id),
        )
        if stored is None:
            raise TribalError("E_CONFLICT", "Chunk identity does not belong to the selected knowledge base and revision.")
        digest = bytes.fromhex(input_hash(format_document_input(title, chunk["heading_path"], chunk["content"])))
        with connection.cursor() as cursor:
            cursor.execute(
                "INSERT INTO embedding_jobs (knowledge_base_id,chunk_id,revision_id,profile_id,input_hash) "
                "VALUES (%s,%s,%s,%s,%s) ON DUPLICATE KEY UPDATE id=id",
                (kb_id, chunk["id"], revision_id, selected_profile, digest),
            )
            result["enqueued"] += int(cursor.rowcount == 1)
    return result


def _profile(connection, profile_id):
    if profile_id is None:
        raise TribalError("E_NOT_FOUND", "Knowledge base has no active embedding profile.",
                          hint="Create and activate an embedding profile first.")
    row = _one(connection, "SELECT * FROM embedding_profiles WHERE id=%s", (_uuid_bytes(profile_id),))
    if row is None:
        raise TribalError("E_NOT_FOUND", "Embedding profile is not registered.")
    return _row(row)


def _knowledge_base(connection, knowledge_base):
    row = _one(connection, "SELECT * FROM knowledge_bases WHERE knowledge_base_key=%s", (knowledge_base,))
    if row is None:
        raise TribalError("E_NOT_FOUND", "Knowledge base is not registered.")
    return _row(row)


def _headings(value):
    return json.loads(value) if isinstance(value, (str, bytes, bytearray)) else value


def _diagnostic(code, message, *, severity="warning", hint=None):
    diagnostic = TribalError(code, message, hint=hint).diagnostic
    diagnostic["severity"] = severity
    return diagnostic


def _generations(kb):
    return {key: kb[key] for key in ("knowledge_generation", "indexing_generation")}


def _indexing_status(connection, knowledge_base_row, profile_id):
    """Read coverage in the caller's snapshot, without owning a transaction."""
    kb = knowledge_base_row
    profile = _profile(connection, profile_id)
    counts = {"total": 0, "embedded": 0, "pending": 0, "oversized": 0, "failed": 0}
    # Match hashes in Python, using the same wrapper as publication and workers.
    # Retain one category per immutable chunk if an operator left stale job rows.
    categories = {}
    priority = {"pending": 0, "failed": 1, "oversized": 2, "embedded": 3}
    with connection.cursor(dictionary=True) as cursor:
        cursor.execute(
            "SELECT c.id,c.content,c.heading_path,r.title,e.embedding,e.dimensions,e.input_hash,"
            "j.state AS job_state,j.input_hash AS job_hash "
            "FROM documents d JOIN document_revisions r ON r.id=d.current_revision_id "
            "JOIN document_chunks c ON c.revision_id=r.id "
            "LEFT JOIN chunk_embeddings e ON e.chunk_id=c.id AND e.profile_id=%s "
            "LEFT JOIN embedding_jobs j ON j.chunk_id=c.id AND j.profile_id=%s "
            "WHERE d.knowledge_base_id=%s AND d.deleted_at IS NULL",
            (_uuid_bytes(profile_id), _uuid_bytes(profile_id), _uuid_bytes(kb["id"])),
        )
        for row in cursor:
            digest = bytes.fromhex(input_hash(format_document_input(row["title"], _headings(row["heading_path"]), row["content"])))
            category = "pending"
            if row["job_hash"] == digest and row["job_state"] in ("oversized", "failed"):
                category = row["job_state"]
            if row["input_hash"] == digest and row["dimensions"] == profile["dimensions"]:
                try:
                    normalize_vector(row["embedding"], dimensions=profile["dimensions"])
                except TribalError:
                    pass
                else:
                    category = "embedded"
            prior = categories.get(row["id"], "pending")
            categories[row["id"]] = max((prior, category), key=priority.__getitem__)
    counts["total"] = len(categories)
    for category in categories.values():
        counts[category] += 1
    return {
        "ok": True, "diagnostics": [], "knowledge_base_id": kb["id"], "profile_id": profile_id,
        **counts, "ready": counts["embedded"] == counts["total"], **_generations(kb),
    }


def indexing_status(db, *, knowledge_base, profile_id=None):
    with db.transaction(readonly=True) as connection:
        kb = _knowledge_base(connection, knowledge_base)
        selected = kb["active_profile_id"] if profile_id is None else profile_id
        return _indexing_status(connection, kb, selected)


def activate_profile(db, *, knowledge_base, profile_id, allow_partial=False):
    if not isinstance(allow_partial, bool):
        raise TribalError("E_ARGUMENT", "allow_partial must be a boolean.")
    with db.transaction() as connection:
        kb = lock_knowledge_base(connection, knowledge_base)
        profile = _profile(connection, profile_id)
        status = _indexing_status(connection, kb, profile_id)
        if not status["ready"] and not allow_partial:
            raise TribalError(
                "E_PROFILE_INCOMPLETE", "Embedding profile does not cover all current chunks.",
                actual={key: status[key] for key in ("pending", "oversized", "failed")},
                hint="Backfill and run the worker, or explicitly activate with allow_partial.",
            )
        if kb["active_profile_id"] != profile_id:
            with connection.cursor() as cursor:
                cursor.execute("UPDATE knowledge_bases SET active_profile_id=%s WHERE id=%s",
                               (_uuid_bytes(profile_id), _uuid_bytes(kb["id"])))
            advance_generations(connection, kb["id"], indexing=True)
            status["indexing_generation"] += 1
        diagnostics = []
        if not status["ready"]:
            diagnostics.append(_diagnostic("W_INDEXING_PARTIAL", "Activated an embedding profile with coverage gaps.",
                                           hint="Backfill this profile and run the embedding worker."))
        return {**status, "diagnostics": diagnostics, "profile": profile, "indexing": status}


def _reuse_vector(connection, *, knowledge_base_id, profile_id, digest, dimensions):
    with connection.cursor(dictionary=True) as cursor:
        cursor.execute(
            "SELECT e.embedding FROM chunk_embeddings e "
            "JOIN document_chunks c ON c.id=e.chunk_id "
            "JOIN document_revisions r ON r.id=c.revision_id "
            "WHERE r.knowledge_base_id=%s AND e.profile_id=%s AND e.input_hash=%s "
            "AND e.dimensions=%s ORDER BY e.chunk_id",
            (_uuid_bytes(knowledge_base_id), _uuid_bytes(profile_id), digest, dimensions),
        )
        rows = cursor.fetchall()
    for row in rows:
        try:
            return normalize_vector(row["embedding"], dimensions=dimensions)
        except TribalError:
            continue
    return None


def _write_vector(connection, *, chunk_id, profile_id, digest, vector):
    # Native VECTOR conversion preserves the already rounded IEEE float32 values.
    with connection.cursor() as cursor:
        cursor.execute(
            "INSERT INTO chunk_embeddings (chunk_id,profile_id,dimensions,embedding,input_hash) "
            "VALUES (%s,%s,%s,STRING_TO_VECTOR(%s),%s) "
            "ON DUPLICATE KEY UPDATE dimensions=VALUES(dimensions),embedding=VALUES(embedding),input_hash=VALUES(input_hash)",
            (chunk_id, _uuid_bytes(profile_id), len(vector), json.dumps(vector, allow_nan=False), digest),
        )
    stored = _one(connection, "SELECT embedding FROM chunk_embeddings WHERE chunk_id=%s AND profile_id=%s",
                  (chunk_id, _uuid_bytes(profile_id)))["embedding"]
    if list(stored) != vector:
        raise TribalError("E_EMBEDDING_VECTOR", "Stored embedding failed the float32 round-trip check.")


def backfill_embeddings(db, *, knowledge_base, profile_id=None):
    with db.transaction() as connection:
        kb = lock_knowledge_base(connection, knowledge_base)
        selected = kb["active_profile_id"] if profile_id is None else profile_id
        profile = _profile(connection, selected)
        with connection.cursor(dictionary=True) as cursor:
            cursor.execute(
                "SELECT c.*,r.title,e.input_hash AS embedding_hash "
                "FROM documents d JOIN document_revisions r ON r.id=d.current_revision_id "
                "JOIN document_chunks c ON c.revision_id=r.id "
                "LEFT JOIN chunk_embeddings e ON e.chunk_id=c.id AND e.profile_id=%s "
                "WHERE d.knowledge_base_id=%s AND d.deleted_at IS NULL ORDER BY c.id",
                (_uuid_bytes(selected), _uuid_bytes(kb["id"])),
            )
            chunks = cursor.fetchall()
        enqueued = reused = 0
        for chunk in chunks:
            headings = _headings(chunk["heading_path"])
            digest = bytes.fromhex(input_hash(format_document_input(chunk["title"], headings, chunk["content"])))
            if chunk["embedding_hash"] == digest:
                continue
            existing = _one(connection,
                            "SELECT id FROM embedding_jobs WHERE chunk_id=%s AND profile_id=%s AND input_hash=%s",
                            (chunk["id"], _uuid_bytes(selected), digest))
            if existing is not None:
                continue
            vector = _reuse_vector(connection, knowledge_base_id=kb["id"], profile_id=selected,
                                   digest=digest, dimensions=profile["dimensions"])
            if vector is not None:
                _write_vector(connection, chunk_id=chunk["id"], profile_id=selected, digest=digest, vector=vector)
                with connection.cursor() as cursor:
                    cursor.execute(
                        "INSERT INTO embedding_jobs (knowledge_base_id,chunk_id,revision_id,profile_id,input_hash,state) "
                        "VALUES (%s,%s,%s,%s,%s,'succeeded')",
                        (_uuid_bytes(kb["id"]), chunk["id"], chunk["revision_id"], _uuid_bytes(selected), digest),
                    )
                reused += 1
            else:
                enqueued += enqueue_chunks(
                    connection, knowledge_base_id=kb["id"], profile_id=selected,
                    chunks=[{**chunk, "revision_id": str(UUID(bytes=chunk["revision_id"])), "heading_path": headings}],
                    title=chunk["title"],
                )["enqueued"]
        if reused:
            advance_generations(connection, kb["id"], indexing=True)
            kb["indexing_generation"] += 1
        return {"ok": True, "diagnostics": [], "knowledge_base_id": kb["id"], "profile_id": selected,
                "enqueued": enqueued, "reused": reused, **_generations(kb)}


def retry_embeddings(db, *, knowledge_base, profile_id=None):
    with db.transaction() as connection:
        kb = lock_knowledge_base(connection, knowledge_base)
        selected = kb["active_profile_id"] if profile_id is None else profile_id
        _profile(connection, selected)
        with connection.cursor() as cursor:
            cursor.execute(
                "UPDATE embedding_jobs j JOIN document_chunks c ON c.id=j.chunk_id AND c.revision_id=j.revision_id "
                "JOIN documents d ON d.current_revision_id=c.revision_id "
                "SET j.state='queued',j.attempts=0,j.available_at=CURRENT_TIMESTAMP(6),"
                "j.claim_token=NULL,j.lease_expires_at=NULL,j.last_error_code=NULL,j.last_error_message=NULL,"
                "j.updated_at=CURRENT_TIMESTAMP(6) "
                "WHERE j.knowledge_base_id=%s AND j.profile_id=%s AND j.state='failed' AND d.deleted_at IS NULL",
                (_uuid_bytes(kb["id"]), _uuid_bytes(selected)),
            )
            retried = cursor.rowcount
        if retried:
            advance_generations(connection, kb["id"], indexing=True)
            kb["indexing_generation"] += 1
        return {"ok": True, "diagnostics": [], "knowledge_base_id": kb["id"], "profile_id": selected,
                "retried": retried, **_generations(kb)}


def _worker_result(job=None, *, state="idle", diagnostics=None):
    return {"ok": True, "diagnostics": diagnostics or [], "job_id": job["id"] if job else None,
            "state": state, "attempts": job["attempts"] if job else 0}


def _job_input(connection, job):
    """Reconstruct only the original identity, including preserved history."""
    row = _one(
        connection,
        "SELECT c.content,c.heading_path,r.title FROM document_chunks c "
        "JOIN document_revisions r ON r.id=c.revision_id "
        "WHERE c.id=%s AND c.revision_id=%s AND r.knowledge_base_id=%s",
        (job["chunk_id"], job["revision_id"], job["knowledge_base_id"]),
    )
    if row is None:
        return None
    text = format_document_input(row["title"], _headings(row["heading_path"]), row["content"])
    return text if bytes.fromhex(input_hash(text)) == job["input_hash"] else None


def _set_job_state(connection, job, state, *, diagnostic=None, delay=0):
    with connection.cursor() as cursor:
        cursor.execute(
            "UPDATE embedding_jobs SET state=%s,claim_token=NULL,lease_expires_at=NULL,"
            "last_error_code=%s,last_error_message=%s,updated_at=CURRENT_TIMESTAMP(6),"
            "available_at=TIMESTAMPADD(MICROSECOND,%s,CURRENT_TIMESTAMP(6)) WHERE id=%s",
            (state, diagnostic["code"] if diagnostic else None,
             diagnostic["message"][:1024] if diagnostic else None, int(delay * 1000000), job["id"]),
        )


def _claim_job(db, knowledge_base):
    """Select candidates without job locks, then acquire the KB gate first."""
    while True:
        with db.transaction(readonly=True) as connection:
            if knowledge_base is not None:
                _knowledge_base(connection, knowledge_base)
            statement = (
                "SELECT j.id,k.knowledge_base_key FROM embedding_jobs j "
                "JOIN knowledge_bases k ON k.id=j.knowledge_base_id "
                "WHERE ((j.state='queued' AND j.available_at<=CURRENT_TIMESTAMP(6)) "
                "OR (j.state='running' AND j.lease_expires_at<=CURRENT_TIMESTAMP(6)))"
            )
            parameters = ()
            if knowledge_base is not None:
                statement += " AND k.knowledge_base_key=%s"
                parameters = (knowledge_base,)
            candidate = _one(connection, statement + " ORDER BY j.available_at,j.id LIMIT 1", parameters)
        if candidate is None:
            return None
        with db.transaction() as connection:
            kb = lock_knowledge_base(connection, candidate["knowledge_base_key"])
            job = _one(
                connection,
                "SELECT *,((state='queued' AND available_at<=CURRENT_TIMESTAMP(6)) OR "
                "(state='running' AND lease_expires_at<=CURRENT_TIMESTAMP(6))) AS claimable "
                "FROM embedding_jobs WHERE id=%s FOR UPDATE", (candidate["id"],),
            )
            if job is None or not job["claimable"]:
                continue
            if job["knowledge_base_id"] != _uuid_bytes(kb["id"]):
                continue
            if job["attempts"] >= 3:
                diagnostic = _diagnostic("E_EMBEDDING_PROVIDER", "Embedding attempts exhausted after lease expiry.",
                                         severity="error", hint="Check provider availability and explicitly retry failed work.")
                _set_job_state(connection, job, "failed", diagnostic=diagnostic)
                advance_generations(connection, kb["id"], indexing=True)
                return {"result": _worker_result(job, state="failed", diagnostics=[diagnostic])}
            token = uuid4().bytes
            with connection.cursor() as cursor:
                cursor.execute(
                    "UPDATE embedding_jobs SET state='running',attempts=attempts+1,claim_token=%s,"
                    "lease_expires_at=TIMESTAMPADD(SECOND,120,CURRENT_TIMESTAMP(6)),"
                    "updated_at=CURRENT_TIMESTAMP(6) WHERE id=%s", (token, job["id"]),
                )
            job.update(attempts=job["attempts"] + 1, claim_token=token, knowledge_base_key=kb["knowledge_base_key"])
            text = _job_input(connection, job)
            if text is None:
                _set_job_state(connection, job, "discarded")
                return {"result": _worker_result(job, state="discarded")}
            profile_id = str(UUID(bytes=job["profile_id"]))
            profile = _profile(connection, profile_id)
            vector = _reuse_vector(connection, knowledge_base_id=kb["id"], profile_id=profile_id,
                                   digest=job["input_hash"], dimensions=profile["dimensions"])
            return {"job": job, "text": text, "profile": profile, "reused_vector": vector}


def _publish_job(db, claim, *, state, vector=None, diagnostic=None, delay=0):
    original = claim["job"]
    with db.transaction() as connection:
        kb = lock_knowledge_base(connection, original["knowledge_base_key"])
        job = _one(connection,
                   "SELECT *,lease_expires_at>CURRENT_TIMESTAMP(6) AS lease_valid "
                   "FROM embedding_jobs WHERE id=%s FOR UPDATE", (original["id"],))
        # Late workers cannot clear or reschedule even their own expired claim.
        if (job is None or job["state"] != "running" or not job["lease_valid"]
                or job["claim_token"] != original["claim_token"]):
            return _worker_result(original, state="discarded")
        identity = ("knowledge_base_id", "chunk_id", "revision_id", "profile_id", "input_hash")
        profile = _profile(connection, claim["profile"]["id"])
        if (any(job[key] != original[key] for key in identity) or profile != claim["profile"]
                or _job_input(connection, job) != claim["text"]):
            _set_job_state(connection, job, "discarded")
            return _worker_result(original, state="discarded")
        if state == "succeeded":
            _write_vector(connection, chunk_id=job["chunk_id"], profile_id=profile["id"],
                          digest=job["input_hash"], vector=vector)
        _set_job_state(connection, job, state, diagnostic=diagnostic, delay=delay)
        if state in ("succeeded", "oversized", "failed"):
            advance_generations(connection, kb["id"], indexing=True)
        return _worker_result(original, state=state, diagnostics=[diagnostic] if diagnostic else [])


def _provider_failure(error):
    """Classify injected providers and the official adapter without raw errors."""
    import openai

    if isinstance(error, _ProviderFailure):
        return error
    if isinstance(error, (TimeoutError, ConnectionError, openai.APIConnectionError)):
        return _ProviderFailure(transient=True)
    if isinstance(error, openai.APIStatusError):
        body = error.body if isinstance(error.body, dict) else {}
        detail = body.get("error", body)
        return _ProviderFailure(
            transient=error.status_code in (408, 409, 429) or error.status_code >= 500,
            oversized=isinstance(detail, dict) and detail.get("code") == "context_length_exceeded",
            retry_after=_retry_after(error.response.headers),
        )
    return _ProviderFailure()


def _profile_count(text, profile):
    configuration = profile["configuration"]
    if not isinstance(configuration, dict):
        raise TribalError("E_ARGUMENT", "Embedding profile configuration is invalid.")
    required = {"wrapper": "tribal-title-headings-v1", "distance": "cosine", "normalization": "l2-float32-v1"}
    limit, encoding = configuration.get("max_input_tokens"), configuration.get("encoding")
    if (any(configuration.get(key) != value for key, value in required.items())
            or isinstance(limit, bool) or not isinstance(limit, int) or limit <= 0 or not isinstance(encoding, str)):
        raise TribalError("E_ARGUMENT", "Embedding profile configuration is invalid.")
    if profile["provider"] == "openai" and profile["model"] in ("text-embedding-3-small", "text-embedding-3-large") and limit > 8192:
        raise TribalError("E_ARGUMENT", "Embedding profile token limit exceeds the supported model limit.")
    try:
        tokens = count_tokens(text, encoding=encoding)
    except ValueError:
        raise TribalError("E_ARGUMENT", "Embedding profile encoding is unavailable.") from None
    return tokens > limit


def run_worker_once(db, provider, *, knowledge_base=None):
    """Claim at most one job and publish with a fresh, leased fencing token."""
    import openai

    claim = _claim_job(db, knowledge_base)
    if claim is None:
        return _worker_result()
    if "result" in claim:
        return claim["result"]
    profile, job = claim["profile"], claim["job"]
    try:
        oversized = _profile_count(claim["text"], profile)
    except TribalError:
        diagnostic = _diagnostic("E_EMBEDDING_PROVIDER", "Embedding profile configuration cannot process input.", severity="error",
                                 hint="Create a supported profile and backfill it.")
        return _publish_job(db, claim, state="failed", diagnostic=diagnostic)
    if oversized:
        diagnostic = _diagnostic("W_EMBEDDING_INPUT_TOO_LARGE", "Complete embedding input exceeds the profile token limit.",
                                 hint="Preserve the source; use a separately configured profile or deliberately revise the document.")
        return _publish_job(db, claim, state="oversized", diagnostic=diagnostic)
    try:
        vector = claim["reused_vector"]
        if vector is None:
            vector = provider.embed(claim["text"], model=profile["model"], dimensions=profile["dimensions"])
        vector = normalize_vector(vector, dimensions=profile["dimensions"])
    except TribalError as error:
        if error.code == "E_EMBEDDING_VECTOR":
            diagnostic = _diagnostic("E_EMBEDDING_VECTOR", "Embedding provider returned an invalid vector.", severity="error",
                                     hint="Check the provider dimensions and numeric output, then retry failed work.")
            return _publish_job(db, claim, state="failed", diagnostic=diagnostic)
        failure = _provider_failure(error)
    except (TimeoutError, ConnectionError, openai.APIError) as error:
        failure = _provider_failure(error)
    else:
        return _publish_job(db, claim, state="succeeded", vector=vector)
    if failure.oversized:
        diagnostic = _diagnostic("W_EMBEDDING_INPUT_TOO_LARGE", "Embedding provider rejected the complete input as oversized.",
                                 hint="Preserve the source and check the configured model input limit.")
        return _publish_job(db, claim, state="oversized", diagnostic=diagnostic)
    state = "queued" if failure.transient and job["attempts"] < 3 else "failed"
    diagnostic = _diagnostic("E_EMBEDDING_PROVIDER", "Embedding provider request failed.",
                             severity="warning" if state == "queued" else "error",
                             hint="A retry is scheduled." if state == "queued" else "Check provider configuration and retry failed indexing work.")
    delay = failure.retry_after if failure.retry_after is not None else min(60, 2 ** job["attempts"])
    return _publish_job(db, claim, state=state, diagnostic=diagnostic, delay=delay if state == "queued" else 0)
