# Chunking, storage, and search implementation contracts

Frozen for the [implementation plan](superpowers/plans/2026-10-20-chunking-storage-search.md), 2026-10-20. These are implementation requirements, not a claim that the APIs already exist. The [Markdown specification](tribal_markdown_spec.md), [chunking strategy](tribal_chunking_strategy.md), and [schema](tribal_schema.md) govern authored validity, segmentation, and the original nine tables. This document fixes the additional names and integration boundaries. Examples here are documentation, not acceptance fixtures.

## Ownership and conventions

| Owner | Files and responsibilities |
|---|---|
| Structure | `parser.py`, `structure.py`, `chunking.py`; shared structural parse and pure chunks. |
| Storage | `storage.py`, all executable migrations under `src/tribal/migrations/`, Docker configuration; connection, migrations, registry/profile rows, generation primitives. |
| Publication | `publication.py`; atomic namespace/revision publication, sources, links, chunk replacement. |
| Embeddings | `embeddings.py`; formatting, provider, vector conversion, durable jobs, coverage and activation. |
| Retrieval | `retrieval.py`; exact ranking, persisted sessions, pinned reads and context. |
| Integration | `cli.py`, package exports, operator documentation. |
| Contracts | `errors.py`, dependency declarations and lock, this document. |
| Tester | All tests and fixture files. Other owners must not author tests or fixtures. |

Use synchronous Python module functions and ordinary dictionaries. Do not add a repository framework, plugin registry, or generic service container. Public result dictionaries are JSON compatible. UUIDs are canonical lowercase non-nil strings; SQL stores their `UUID(value).bytes`. SHA-256 values are lowercase 64-character hex strings; SQL stores `bytes.fromhex(value)`. Chunk/job IDs are positive integers. Timestamps in results are UTC RFC3339 strings ending in `Z`; SQL uses UTC `DATETIME(6)`. JSON columns deserialize to objects/arrays, never JSON strings. Ranges are half-open canonical UTF-8 byte offsets, not character offsets. Nullable keys are present with `None`, not omitted. Additional documented measurement fields are allowed; do not rename the required keys.

Top-level operational service functions return `{"ok": True, "diagnostics": [...], ...}` on success. All abbreviated service-result field lists below inherit these `ok` and `diagnostics` keys. Transaction-local helpers use the compact return shapes explicitly specified for them. Authored validation failures return `ok=False` with diagnostics and no writes. The pure validator/chunker uses `valid`, preserving the parser API. Operational failures raise `tribal.errors.TribalError`; the CLI serializes `error.as_dict()` as `{"ok": False, "diagnostics": [...]}`. A failed atomic operation never returns a partial success. Programming errors are not converted into authored diagnostics. Never include credentials, SQL connection strings, provider response bodies, or full notes in operational errors.

`TribalError(code, message, *, path=None, field=None, expected=None, actual=None, hint=None)` exposes `.code`, `.diagnostic`, and `.as_dict()`. Its diagnostic has all parser-envelope keys: `code`, `severity`, `message`, `path`, `line`, `column`, `field`, `expected`, `actual`, `hint`, `excerpt`. Operational `line`, `column`, and `excerpt` are `None`; callers use the existing parser envelope for source-located problems. `actual` and `expected` must already be safe JSON values. Error hints should tell an operator how to recover.

| Code | Meaning |
|---|---|
| `E_DATABASE` | Database connection/query failure; transaction rolled back. |
| `E_MIGRATION` | Migration failure, unsupported schema, or applied checksum mismatch. |
| `E_NOT_FOUND` | Requested knowledge base, domain, document, revision, profile, or chunk unavailable. |
| `E_CONFLICT` | Expected chunk set or immutable configuration differs; reload and retry. |
| `E_REVISION_CONFLICT` | Changed existing document has a stale expected revision; reload and reconcile. |
| `E_BASE_REVISION_REQUIRED` | Changed existing document has no base revision token. |
| `E_ASSIGNMENT` | Document knowledge base/domain does not match registered assignment. |
| `E_DELETED` | Ordinary ingest attempted to modify/restore a soft-deleted document. |
| `E_CHUNK_INVARIANT` | Structural/range reconstruction failed; publish no chunks. |
| `E_EMBEDDING_PROVIDER` | Provider unavailable/rejected input; safe summary only. |
| `E_EMBEDDING_VECTOR` | Wrong dimensions, nonfinite values, zero norm, or invalid float32 round trip. |
| `E_PROFILE_INCOMPLETE` | Profile activation refused due to coverage gaps. |
| `E_CURSOR_INVALID` | Malformed cursor or query/filter/mode mismatch. |
| `E_CURSOR_EXPIRED` | TTL elapsed, generation changed, or profile changed. |
| `E_SEARCH_CAPACITY` | Complete candidate scan/session cannot be materialized within configured capacity; no partial page. |
| `E_CONTEXT_BUDGET_EXCEEDED` | Complete matched chunk exceeds source budget. |
| `E_ARGUMENT` | Invalid operational parameter, such as page size or negative budget. |
| `E_IO` | CLI filesystem access failed. |
| `W_OVERSIZED_BLOCK` | Preserved unit exceeds 4,096 source bytes; valid document. |
| `W_EMBEDDING_INPUT_TOO_LARGE` | Complete input exceeds profile token limit; source stays searchable lexically. |
| `W_INDEXING_PARTIAL` | Operator explicitly activated a profile with gaps. |

Existing parser codes remain unchanged, including path and metadata diagnostics. Codes identify conditions, not Python subclasses. Stale worker outcomes are normal result states (`discarded`), not authored validation errors.

## Structure and chunking

```python
# tribal.chunking
chunk_document(content: str | bytes, *, path="note.md", revision_id=None,
               knowledge_base=None, domains=None) -> dict
```

Return required keys `valid`, `path`, `diagnostics`, `document_id`, `revision_id`, `content_hash`, `chunker_version`, `body_start_byte`, `chunks`. `document_id` comes from metadata `id`; preview `revision_id` is the supplied value or `None`. Invalid inputs return `chunks=[]`; identity/hash/body start may be `None` when unavailable. Return the parser's complete diagnostics, including warnings. Version is always `tribal-structure-bytes-v1`. `body_start_byte` is the length in UTF-8 bytes of canonical frontmatter including delimiters and its terminating LF. Empty body means no chunks.

Every chunk has `revision_id`, `ordinal`, `heading_path`, `section_anchor`, `start_byte`, `end_byte`, `content`, `chunker_version`. No preview chunk `id` is allocated. SQL assigns `id` at publication. `content` is exactly `canonical_markdown.encode("utf-8")[start_byte:end_byte].decode("utf-8")`. Ordered ranges cover `[body_start_byte, len(canonical_utf8))` once, with no gaps. Broken invariants raise `E_CHUNK_INVARIANT`, not `valid=False`.

`W_OVERSIZED_BLOCK` uses the normal diagnostic envelope with `expected=4096` and `actual={"start_byte": int, "end_byte": int, "bytes": int, "unit_kind": str}`. Here `bytes` is `end_byte - start_byte`, including attached source gaps. `unit_kind` is one of `paragraph`, `heading`, `table`, `code`, `mermaid`, `math`, `list_item`, `list`, `blockquote`, `definition`, `opaque`, or `other`, as appropriate to the emitted intact unit. `line` and `column` locate the unit start in normalized submitted source, using the transport mapping. Keep the structured `actual` object; do not stringify it.

```json
{
  "valid": true, "path": "note.md", "diagnostics": [],
  "document_id": "91b188c2-96f4-45a9-aada-e424e960ad84",
  "revision_id": null, "content_hash": "<64 lowercase hex characters>",
  "chunker_version": "tribal-structure-bytes-v1", "body_start_byte": 300,
  "chunks": [{"revision_id": null, "ordinal": 0, "heading_path": [],
    "section_anchor": null, "start_byte": 300, "end_byte": 305,
    "content": "Text\n", "chunker_version": "tribal-structure-bytes-v1"}]
}
```

`tribal.structure` is shared internal implementation, not a second public parser. Structure owner chooses its concrete representation, exposing canonical body start, mapping to submitted locations, root-heading sections with unique source-range identity, protected ranges, reliable immediate list-item boundaries, and heading plain-text eligibility. Publication consumes `chunk_document`; context retrieval uses this shared section model or stored-revision `chunk_document` output, never nullable heading anchors as identities. Existing `validate_document`/`validate_vault` signatures and output stay compatible.

## Database and registry

```python
# tribal.storage
class Database:
    def __init__(self, **connect_options): ...
    def transaction(self, *, readonly=False): ...  # context manager yielding MySQL connection
    def close(self) -> None: ...

migrate(db: Database) -> dict
ensure_knowledge_base(db, *, key, name, description=None) -> dict
ensure_domain(db, *, knowledge_base, key, name, description=None) -> dict
ensure_profile(db, *, key="openai-text-embedding-3-small-v1",
               provider="openai", model="text-embedding-3-small",
               dimensions=1536, configuration=None, model_version=None) -> dict
get_knowledge_base(db, *, knowledge_base) -> dict
get_profile(db, *, profile_id=None, key=None) -> dict
lock_knowledge_base(connection, knowledge_base) -> dict
advance_generations(connection, knowledge_base_id, *, knowledge=False,
                    indexing=False) -> None
```

`knowledge_base` is a registered key throughout public service functions; `profile_id`, `document_id`, `revision_id` are UUID strings. `get_profile` requires exactly one of `profile_id`/`key`. Registry results contain `ok`, `diagnostics`, and respectively `knowledge_base`, `domain`, or `profile` row dictionaries. `get_knowledge_base` row contains the added generations and active profile. `ensure_*` is idempotent for matching configuration; differing existing immutable profiles raise `E_CONFLICT`. Domain ownership is enforced. Empty KB initialization selects its initial profile through `activate_profile`; no profile is silently selected on reads. A migration result includes `applied` (ordered version strings) and `schema_version` (latest applied version or `None`).

`Database` passes connector options through, while enforcing `autocommit=False`, UTC, `utf8mb4`, strict SQL mode, and sufficient packet capacity. Each transaction owns a connection, starts explicitly, commits once on successful exit, rolls back on exceptions, and closes the connection. A readonly transaction provides a consistent snapshot; mutation transactions use current locking reads before writes. Connections/cursors do not escape their context. Nested transactions are unsupported. `close()` is safe after use. No implicit commits in service helpers. Database setup/migration is the only DDL boundary.

`lock_knowledge_base` resolves key and performs `SELECT ... FOR UPDATE`, returning the locked row with UUID/hash fields normalized as above. Every KB mutation locks this row first; document locks follow ascending UUID bytes. `advance_generations` receives an already locked KB and increments each requested generation once. The transaction owner calls it once after combining all effects. Service functions own their transactions; they do not call another transaction-owning service from inside one. Internal SQL helpers may accept the current connection.

## Frozen SQL mapping

Storage is the sole migration author. Implement every column/index/constraint of the nine-table [schema](tribal_schema.md), plus these additions. All tables are InnoDB. Existing table/column names, `VECTOR(16383)`, UUID/hash representations, full-text indexes, revision ownership FKs, and byte capacity constraints remain authoritative, subject to the equivalent vector-dimension enforcement below. Do not substitute MariaDB, JSON vectors, or SQL `DISTANCE()` requirements.

| Table | Added columns / constraints |
|---|---|
| `knowledge_bases` | `active_profile_id BINARY(16) NULL` FK to `embedding_profiles.id`; `knowledge_generation BIGINT UNSIGNED NOT NULL DEFAULT 0`; `indexing_generation BIGINT UNSIGNED NOT NULL DEFAULT 0`. Add FK after profiles exist. |
| `schema_migrations` | `version VARCHAR(64)` PK; `checksum BINARY(32) NOT NULL`; `applied_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6)`. Hash exact migration file bytes. |
| `embedding_jobs` | Columns and constraints below. |
| `search_sessions` | Columns and constraints below. |
| `search_session_results` | Columns and constraints below. |

The storage owner verified on MySQL 9.7.2 that `CHECK (VECTOR_DIM(embedding) = dimensions)` is rejected with server error 3064. The approved equivalent is both `BEFORE INSERT` and `BEFORE UPDATE` triggers on `chunk_embeddings` that reject `VECTOR_DIM(NEW.embedding) <> NEW.dimensions` with `SIGNAL SQLSTATE '45000'` (server error 1644). Keep native `VECTOR(16383)`, the immutable profile dimensions, and the `(profile_id, dimensions)` foreign key. Both write paths must reject mismatched dimensions. Executed, versioned storage migrations and their real-server checks are the authority for exact working DDL; update the schema document to match this tested enforcement instead of preserving an unexecutable CHECK. Package migration SQL as `tribal` package data using `migrations/*.sql` so installed wheels retain it.

`embedding_jobs` columns:

| Name | SQL type / meaning |
|---|---|
| `id` | `BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY` |
| `knowledge_base_id` | `BINARY(16) NOT NULL`, FK knowledge bases |
| `chunk_id` | `BIGINT UNSIGNED NOT NULL`; intentionally no FK: keep stale identity after rechunk/removal |
| `revision_id` | `BINARY(16) NOT NULL`, FK revisions; checks original ownership |
| `profile_id` | `BINARY(16) NOT NULL`, FK profiles |
| `input_hash` | `BINARY(32) NOT NULL` |
| `state` | `ENUM('queued','running','succeeded','oversized','failed','discarded') NOT NULL DEFAULT 'queued'` |
| `attempts` | `INT UNSIGNED NOT NULL DEFAULT 0` |
| `available_at` | `DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6)` |
| `claim_token` | `BINARY(16) NULL`; new UUID for every claim, never reused |
| `lease_expires_at` | `DATETIME(6) NULL`; hard publication deadline, 120 seconds after claim |
| `last_error_code` | `VARCHAR(64) NULL`; safe diagnostic code |
| `last_error_message` | `VARCHAR(1024) NULL`; bounded safe description |
| `created_at`, `updated_at` | `DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6)`; updated_at maintained by worker |

Unique `(chunk_id, profile_id, input_hash)`; claim index `(state, available_at, id)`; KB status index `(knowledge_base_id, profile_id, state)`. Enforce running iff both `claim_token` and `lease_expires_at` are non-NULL; nonrunning rows clear both. State transitions and attempts cap are checked by worker. Check KB/revision ownership under KB lock. `chunk_id` intentionally survives old chunk deletion; never redirect to a same-ordinal chunk. Expired running rows are eligible for reclaim with a fresh token if attempts remain, otherwise terminal failure. Reclaim/lease changes alone do not change generations; terminal state/readiness does.

`search_sessions` columns:

| Name | SQL type / meaning |
|---|---|
| `id` | `BINARY(16) PRIMARY KEY` |
| `knowledge_base_id` | `BINARY(16) NOT NULL`, FK knowledge bases |
| `profile_id` | `BINARY(16) NULL`, FK profiles; active profile captured even for lexical mode |
| `query` | `TEXT NOT NULL`; original query |
| `query_vector` | `VECTOR(16383) NULL`; exact float32 query vector, NULL for lexical |
| `mode` | `ENUM('semantic','lexical','hybrid') NOT NULL` |
| `lexical_mode` | `ENUM('fulltext','literal') NOT NULL`; selected actual ranking after fallback |
| `parameters` | `JSON NOT NULL`; canonical request parameters described below |
| `knowledge_generation`, `indexing_generation` | `BIGINT UNSIGNED NOT NULL` |
| `result_count` | `BIGINT UNSIGNED NOT NULL` |
| `created_at` | `DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6)` |
| `expires_at` | `DATETIME(6) NOT NULL`; database time + 15 minutes |

Index `(expires_at)` and `(knowledge_base_id, created_at)`; require parameters JSON object. `parameters` stores original `query`, requested `mode`, requested `lexical_mode`, sorted/deduplicated `domains`, sorted/deduplicated `statuses`, and `include_deleted`. Store requested lexical mode even if actual fallback was literal. Page size is not part of search identity. No query truncation.

`search_session_results` columns: `session_id BINARY(16) NOT NULL` FK sessions `ON DELETE CASCADE`; `rank BIGINT UNSIGNED NOT NULL` (one-based); `document_id BINARY(16) NOT NULL` FK documents; `revision_id BINARY(16) NOT NULL` FK revisions; `chunk_id BIGINT UNSIGNED NOT NULL` (no FK, so rechunk does not block retained sessions); `score DOUBLE NOT NULL`; `semantic_score DOUBLE NULL`; `lexical_score DOUBLE NULL`; primary key `(session_id, rank)`; unique `(session_id, chunk_id)`; check `rank > 0`. Publication checks current generations before serving a page; stale sessions are rejected before dereferencing replaced chunk IDs. Results need no duplicated text/metadata snapshots because revisions are immutable and stale generations invalidate replaced derived data.

Search session creation does not advance generations. Compute and materialize within a consistent read view; lock/check the KB generations/profile again before session publication so a racing mutation cannot validate stale results. Generation changes after publication invalidate continuation. Service authors may use explicit connector dictionary cursors and parameterized SQL against these frozen columns; there is no extra generic repository API to invent.

## Publication

```python
# tribal.publication
ingest_vault(db, documents: dict[str, str | bytes], *, knowledge_base,
              author_type="human", author_id="cli", change_summary=None) -> dict
rechunk_revision(db, *, knowledge_base, document_id, revision_id=None,
                  expected_chunk_ids=None) -> dict
set_document_deleted(db, *, knowledge_base, document_id, expected_revision,
                     deleted=True) -> dict
```

`documents` is a submitted batch, not a deletion list. Domain comes from each note and must be registered. Changed existing documents require `tribal_base_revision` matching their current revision. Unchanged canonical content and path are a no-op even with a stale or absent token. For a new document, ignore a syntactically valid foreign base token; no history is imported. Ingestion initially accepts expected revisions only through the transport token, with no separate expected-revisions mapping. Rechunk `revision_id=None` means resolve current revision. `expected_chunk_ids` is the exact ordered previous ID list; `None` means capture before computation and recheck under lock. Rechunk creates no authored revision. Stale rechunk expectations raise `E_CONFLICT`; changed ingestion uses `E_REVISION_CONFLICT` or `E_BASE_REVISION_REQUIRED` as specified by the Markdown contract.

Ingest success includes `knowledge_base_id`, generations, `documents` (path-keyed outcomes), and `summary` integer counts `created`, `updated`, `unchanged`, `chunks`, `jobs`. Each outcome has `document_id`, `revision_id`, `previous_revision_id`, `action` (`created`, `updated`, `unchanged`), `path`, `chunk_ids`, and `diagnostics`. `chunks`/`jobs` counts are newly published/enqueued rows. Validation failure includes `ok=False`, collected diagnostics, and the validation result as `validation`; commit nothing. Unchanged input preserves revision and chunks, makes no repair jobs, and changes no generation. Path-only changes do create revisions. Rechunk success includes `document_id`, `revision_id`, `old_chunk_ids`, `chunk_ids`, `jobs`, and generations.

`set_document_deleted` is the explicit delete/restore operation. Require `expected_revision` to match the current head even when the requested lifecycle state is already set; stale expectations raise `E_REVISION_CONFLICT`. Return `document_id`, `revision_id`, `deleted` (the resulting boolean), `changed` (whether lifecycle changed), `knowledge_generation`, and `indexing_generation`, plus the standard service envelope. Lock the KB before the document, preserve every authored revision/chunk/vector, and refresh links from all current sources atomically when lifecycle changes. A restore rechecks the complete current namespace and portable path reservations under the lock. Ordinary ingestion never restores a deleted note. A changed lifecycle advances knowledge generation once; an unchanged lifecycle advances neither generation. Lifecycle alone does not advance indexing generation or perform implicit indexing repair.

Build the full namespace with unaffected and soft-deleted reservations; use shared parser validation. Compute chunks before locking, recheck under KB lock, stage occupied path swaps through `.tribal-staging`, and publish revisions/sources/links/chunks/pointers/jobs in one transaction. Refresh binding targets for links from all current revisions, including unchanged notes. Keep historical revisions/chunks/embeddings on ordinary edits; explicit rechunk replaces only the selected revision's entire chunk set with fresh IDs, deleting dependent vectors before old chunks and discarding stale jobs. Increment knowledge generation for accepted heads/paths/lifecycle/domain changes and indexing generation for chunk-set changes, each once per commit. Accepted source content does not depend on provider availability.

## Embeddings, profiles, and worker

```python
# tribal.embeddings
format_document_input(title: str, heading_path: list[str], content: str) -> str
input_hash(text: str) -> str
count_tokens(text: str, *, encoding="cl100k_base") -> int
normalize_vector(values, *, dimensions: int) -> list[float]
class OpenAIProvider:
    def __init__(self, *, api_key=None): ...
    def embed(self, text: str, *, model: str, dimensions: int) -> list[float]: ...
class DeterministicProvider:
    def embed(self, text: str, *, model: str, dimensions: int) -> list[float]: ...
enqueue_chunks(connection, *, knowledge_base_id, profile_id, chunks, title) -> dict
backfill_embeddings(db, *, knowledge_base, profile_id=None) -> dict
retry_embeddings(db, *, knowledge_base, profile_id=None) -> dict
run_worker_once(db, provider, *, knowledge_base=None) -> dict
indexing_status(db, *, knowledge_base, profile_id=None) -> dict
activate_profile(db, *, knowledge_base, profile_id, allow_partial=False) -> dict
```

`enqueue_chunks` is the shared transaction-local publication helper, not a transaction-owning service. The caller already holds the KB lock and owns commit/rollback and generation updates. `knowledge_base_id` is a UUID string and `chunks` contains persisted chunk dictionaries with `id`, `revision_id`, `heading_path`, and `content`. Return exactly `{"enqueued": int, "reused": int, "diagnostics": list}`. `profile_id=None` returns zero counts and no diagnostics. Format/hash complete inputs to deduplicate jobs, but perform no provider call or token counting during ingestion. An implementation may only enqueue (`reused=0`); workers/backfill handle compatible same-KB reuse. Existing vector/job identities do not create duplicate jobs. The helper never silently selects an active profile.

Providers need only the `embed` method above; use structural duck typing, not an abstract framework. A deterministic provider is for offline tests and must return the same finite, nonzero vector for identical model/dimensions/input; its precise algorithm is not a ranking contract. Profile omitted in transaction-owning backfill/retry/status functions means KB active profile; absence raises `E_NOT_FOUND`. `knowledge_base=None` on worker permits any eligible KB, with claims ordered by availability then job ID. The provider call is always outside transactions.

Initial immutable profile has key `openai-text-embedding-3-small-v1`, provider `openai`, model `text-embedding-3-small`, model_version `None`, dimensions `1536`, configuration exactly:

```json
{"wrapper":"tribal-title-headings-v1","encoding":"cl100k_base","max_input_tokens":8192,"distance":"cosine","normalization":"l2-float32-v1"}
```

`configuration=None` means this configuration only for the default model/provider/dimensions; nondefault profiles must explicitly supply valid configuration. Equality is JSON object equality, independent of key order. Once created, every profile field is immutable.

Wrapper is `"Title: " + title + "\nHeadings: " + json.dumps(heading_path, ensure_ascii=False, separators=(",", ":")) + "\n\n" + content`; append nothing. Hash exact UTF-8 bytes. Query input is the original query, with no wrapper. Count via `tiktoken.get_encoding(encoding).encode(text, disallowed_special=())`, treating special-looking authored strings as source. An input over 8,192 tokens is oversized, never truncated. OpenAI adapter uses `OpenAI(api_key=..., timeout=30.0, max_retries=0)` and `client.embeddings.create(model=model, input=text, dimensions=dimensions, encoding_format="float")`.

Normalize finite nonzero vectors in float64, convert every component to IEEE float32, validate float32 components and norm again, and return those round-tripped components. Persist/read vector bytes consistently with MySQL vector representation. Rank cosine using float64 accumulation and norms over persisted float32 components, not rounded scores or a unit-norm assumption. Query vectors use the same normalization and float32 round trip and are persisted exactly. Normalize/revalidate reused provider outputs as well.

Queue identity is `(chunk_id, profile_id, input_hash)`, reuse restricted to the same KB and exact profile/input hash. Backfill only current, nondeleted chunk sets; skip existing job/vector identities, reusing compatible embeddings where possible. It returns `enqueued` and `reused` counts and generations. Retry resets eligible terminal `failed` jobs to queued/attempts zero; oversized/discarded/succeeded rows are not retried. It returns `retried`. Reset readiness changes indexing generation once. Backfill that publishes reused vectors advances indexing generation once; mere enqueue/claim does not.

Claim one job using DB time, increment attempts, generate a fresh claim UUID, and set lease deadline +120 seconds. Maximum three attempts. Retry connection/timeouts, 408, 409, 429, and 5xx durably with `available_at` honoring Retry-After, otherwise bounded exponential backoff; never sleep holding a transaction. Terminal provider failures get safe code/message; malformed vectors are terminal. A result publisher locks the KB first then checks running state, exact token, unexpired deadline, original chunk/revision/KB, profile, and reconstructed hash. Commit vector+success+indexing generation atomically. A stale worker cannot clear, fail, reschedule, or overwrite a newer claim. Stale publication returns `state="discarded"` without mutating newer ownership. Exhausted expired jobs become failed under the KB lock and advance indexing generation.

Worker success result keys: `ok`, `diagnostics`, `job_id` (or None), `state` (`idle`, `succeeded`, `queued`, `oversized`, `failed`, `discarded`), `attempts` (0 when idle). `queued` means a durable retry, not an active lease. Embedding provider errors handled by the worker return this job result; immediate query-vector provider errors raise `E_EMBEDDING_PROVIDER`.

Retrieval may use the shared private `_indexing_status(connection, knowledge_base_row, profile_id)` helper to obtain the ordinary status result envelope from its existing read snapshot. This helper does not start/commit a transaction or acquire a new snapshot. It is an internal integration boundary, not a top-level public service.

Status result keys: `knowledge_base_id`, `profile_id`, `total`, `embedded`, `pending`, `oversized`, `failed`, `ready`, and generations. Counts partition eligible current nondeleted chunks: valid vector wins as embedded; otherwise oversized terminal job, otherwise failed terminal job, otherwise pending (including missing/queued/running jobs). `ready` means `pending == oversized == failed == 0`; empty sets are ready. Activation requires complete coverage unless `allow_partial`; return profile/status and `W_INDEXING_PARTIAL` when gaps are accepted. It runs under KB lock and changes indexing generation only if active profile changes.

## Search and revision-pinned reads

```python
# tribal.retrieval
search(db, query: str, *, knowledge_base, provider=None, mode="semantic",
       lexical_mode="fulltext", domains=None, statuses=None,
       include_deleted=False, limit=20, cursor=None,
       max_candidates=100000) -> dict
read_document(db, *, knowledge_base, document_id, revision_id=None,
              start_byte=None, end_byte=None) -> dict
read_context(db, *, knowledge_base, document_id, revision_id, chunk_id,
             budget_bytes=65536) -> dict
```

`domains` is a list of registered domain keys, default all. `statuses=None` means `["active"]`; explicit list permits `active`, `superseded`, `archived`. Lists normalize by sort/dedup for continuation identity. Empty explicit lists match nothing. `include_deleted=False` excludes soft deletion. Only current revisions are search candidates. `limit` is integer 1..100; `max_candidates` is a positive capacity guard over eligible candidates, with no silent partial scan. `provider` is required for semantic/hybrid first page and unused for lexical or continuation. An empty/whitespace query raises `E_ARGUMENT`; preserve all other query bytes.

Semantic compares every eligible active-profile vector. Full-text lexical score is natural-language `MATCH(title,summary)` relevance + `MATCH(content)` relevance. Candidate is eligible when either term is positive, and document relevance contributes to every owning chunk. Literal fallback occurs only when the eligible full-text ranking is empty, or explicit `lexical_mode="literal"`; match whole original query as a case-sensitive Unicode substring independently in title, summary, content. Score counts matching fields (0..3), not occurrences. SQL wildcard `%`/`_` have no special meaning. Hybrid uses full untruncated rankings, equal-weight reciprocal rank fusion `1/(60+semantic_rank) + 1/(60+lexical_rank)` with missing terms zero. Tie order is document UUID bytes then ordinal in all rankings. Semantic failures raise, never fall back.

Search result keys: `ok`, `diagnostics`, `query`, `mode`, actual `lexical_mode`, `profile_id`, `knowledge_generation`, `indexing_generation`, `indexing` (status counts), `hits`, `next_cursor`, `expires_at`. A hit has `rank`, `score`, nullable `semantic_score` and `lexical_score`, plus `document_id`, `revision_id`, `chunk_id`, `ordinal`, `path`, `title`, `summary`, `domain`, `heading_path`, `section_anchor`, `start_byte`, `end_byte`, `content`, `verification_state`, `verified_at`, `scope`, `contexts`, `sources`, `applicability`. `sources` is the owning revision's evidence records; `applicability` is always `"unknown"` absent domain-specific rules. Returning verification metadata does not independently verify claims.

A first page materializes every ranked result in a session. Cursor is an opaque string carrying session ID and next one-based rank; implementations must validate types/bounds and bind it to the stored exact parameter object. Continuation repeats query/filters/mode and rejects changed parameters with `E_CURSOR_INVALID`. A cursor presented for a different knowledge base also raises `E_CURSOR_INVALID`; same-knowledge-base generation/profile changes and TTL expiry raise `E_CURSOR_EXPIRED`. It loads the stored vector/ranking without another provider call. Reject DB time >= expires_at or changed KB generation/profile with `E_CURSOR_EXPIRED`. Fresh session expiry is DB time +15 minutes; continuation does not extend it. Changing limit is permitted. No public cursor encoding is guaranteed. Scan/session capacity failure returns no hits through `E_SEARCH_CAPACITY`.

`read_document` requires the requested revision to belong to the document and KB; omitted revision means current. Historical revisions remain readable. Result has `document_id`, `revision_id`, `path` (historical path), `title`, `metadata`, `content_hash`, `start_byte`, `end_byte`, `content`, plus standard operational envelope. Default range covers the complete canonical Markdown including frontmatter. Explicit endpoints must be paired, in bounds, and UTF-8 boundaries; invalid ranges raise `E_ARGUMENT`. Returned `content` is the exact canonical slice, never a reserialization.

`read_context` verifies the three identities and uses that revision's section source range. Select complete matched chunk first, then same-section Mermaid chunks by distance between ranges and source start, then other same-section chunks in that order while budget permits. Distance is zero for adjacent ranges, otherwise the number of bytes between them. A candidate that does not fit is omitted; continue considering smaller later candidates. Deduplicate ranges, return selections in source order, and count only source bytes against budget. Never use another section/revision or require an embedding for a diagram. Matched chunk above budget raises `E_CONTEXT_BUDGET_EXCEEDED`.

Context result has `document_id`, `revision_id`, `matched_chunk_id`, `section_start_byte`, `section_end_byte`, `budget_bytes`, `used_bytes`, `chunks` (full stored chunk objects), `omitted_chunk_ids` (source order), `omitted_bytes` (sum of omitted same-section content bytes), and `complete` (no same-section omissions). Source gaps between selected chunks must stay visible as separate ranges; do not imply that concatenated disjoint selections are a contiguous source slice.

## CLI integration contract

Existing `tribal validate` behavior and exit codes stay intact. Add these commands, with `--json` on each leaf command; the integration owner implements parsing and exports only after components land:

```text
tribal chunk PATH [--knowledge-base KEY] [--domain KEY ...] [--revision-id UUID]
tribal db migrate
tribal kb ensure KEY --name NAME [--description TEXT]
tribal domain ensure KEY --knowledge-base KEY --name NAME [--description TEXT]
tribal ingest PATH --knowledge-base KEY [--author-type human|agent|system] [--author-id ID] [--change-summary TEXT]
tribal rechunk DOCUMENT_UUID --knowledge-base KEY [--revision-id UUID]
tribal profile ensure [--key KEY] [--provider openai] [--model MODEL] [--dimensions N] [--configuration JSON]
tribal profile activate UUID --knowledge-base KEY [--allow-partial]
tribal index backfill --knowledge-base KEY [--profile-id UUID]
tribal index retry --knowledge-base KEY [--profile-id UUID]
tribal index worker [--knowledge-base KEY] [--once]
tribal index status --knowledge-base KEY [--profile-id UUID]
tribal search QUERY --knowledge-base KEY [--mode semantic|lexical|hybrid] [--lexical-mode fulltext|literal] [--domain KEY ...] [--status STATUS ...] [--include-deleted] [--limit N] [--cursor TOKEN]
tribal read DOCUMENT_UUID --knowledge-base KEY [--revision-id UUID] [--start-byte N --end-byte N]
tribal context DOCUMENT_UUID REVISION_UUID CHUNK_ID --knowledge-base KEY [--budget-bytes N]
```

`PATH` accepts a note or recursively selected vault directory using existing CLI exclusions; ingestion passes the collected batch to the service. No environment probing or Git requirement. DB connection environment names: `TRIBAL_DB_HOST` (default `127.0.0.1`), `TRIBAL_DB_PORT` (3306), `TRIBAL_DB_USER`, `TRIBAL_DB_PASSWORD`, `TRIBAL_DB_NAME` (`tribal`). OpenAI credentials use `OPENAI_API_KEY`. JSON emits the library result envelope. Exit 0 on success/warnings, 1 on authored validation failure, 2 on usage/I/O or operational failure. Text output renders actionable diagnostic details. Continuous worker repeats independent claims and sleeps only outside DB transactions; `--once` performs exactly one `run_worker_once` call.

## Dependency and documentation verification

Python remains `>=3.12`. Direct runtime requirements are pinned in `pyproject.toml`; `requirements.lock` contains the complete hash-checked runtime resolution for CPython 3.12 on Linux. Install runtime with `python -m pip install --require-hashes -r requirements.lock`, then install this local project with `python -m pip install --no-deps -e .`. Test extras are separately declared; this runtime lock does not claim to lock test tools or build isolation. Regenerate using an isolated `pip-tools==7.6.2` environment and the command recorded in its header. Updating dependencies is an explicit lock refresh.

Verified 2026-10-20 against package metadata and primary documentation:

- Published pinned releases: [mysql-connector-python 26.7.0](https://pypi.org/project/mysql-connector-python/26.7.0/), [openai 3.35.1](https://pypi.org/project/openai/3.35.1/), and [tiktoken 0.14.0](https://pypi.org/project/tiktoken/0.14.0/). Resolver must verify compatibility with Python 3.12.
- [OpenAI embedding guide](https://developers.openai.com/api/docs/guides/embeddings) specifies the 8,192-token model limit, `cl100k_base` for third-generation embeddings, and cosine use. [OpenAI Python SDK documentation](https://github.com/openai/openai-python#retries) documents `max_retries=0` and configurable timeouts. Tribal sets 30 seconds and owns durable retries.
- [Connector/Python introduction](https://dev.mysql.com/doc/connector-python/en/connector-python-introduction.html) establishes DB-API support; [transaction API](https://dev.mysql.com/doc/connector-python/en/connector-python-api-mysqlconnection-start-transaction.html) defines explicit transaction start. [MySQL vector documentation](https://dev.mysql.com/doc/refman/9.7/en/vector.html) defines VECTOR storage; the storage owner must verify driver vector round trips against real MySQL 9.7.
- [tiktoken source/API](https://github.com/openai/tiktoken) provides explicit encoding selection. Tokenizer encoding assets may need initial network/cache population; pinning the package does not itself prove an offline tokenizer smoke test.

Dependency resolution and parser regression tests establish installation compatibility only. Real Docker/MySQL integration and credentialed OpenAI calls remain separate acceptance evidence.
