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
