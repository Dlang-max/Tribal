# Project knowledge storage

`tribal_kb.service.KnowledgeBaseService` exposes the internal note tools, graph,
and request receipts. It requires a project ID, `SeaweedObjectStore`, and
`MySQLCatalog`. An optional `OpenAIEmbeddingClient` enables semantic ranking;
without `OPENAI_API_KEY`, search remains lexical. Storage adapters have injectable
clients for controlled checks; the runtime always configures real adapters.

Source Markdown remains byte-for-byte UTF-8 in immutable, project-prefixed
SeaweedFS S3 objects. MySQL stores current note manifests, historical revision
manifests, derived chunks, and project-scoped request receipts. Create the MySQL 8
database and SeaweedFS bucket before starting; catalog initialization creates only
its tables. Their NO PAD binary collation preserves opaque IDs exactly, including
case and trailing spaces. The SQL user needs table creation and read/write permissions.

Publication takes a MySQL project-row lock, checks expected revisions and create
collisions, stages the complete proposed vault, and runs the existing v1
validator. Validation covers note structure and local graph rules; the curator
must independently verify source claims. IDs and paths remain stable. Archive
changes lifecycle metadata and keeps earlier objects and link targets.

After validation, immutable objects upload before one SQL transaction publishes
all new manifests, revision history, and the successful request receipt. Failed
uploads or SQL commits leave no partially visible batch. Unpublished objects may
remain as harmless orphans. A retry with the same request ID and payload hash
returns the saved successful outcome; reusing its ID with a different hash raises
an error. Multiple curators may reason and search concurrently; only publication
for the same project coordinates through SQL.

Overview and heading/content chunks are derived after publication. Optional
OpenAI requests use `text-embedding-3-small`, pinned to 1536 dimensions by default.
Provider errors never reject a valid Markdown write. Delayed results attach only
when their source note revision is still current. Search excludes archived and
superseded notes and ignores incompatible model, dimension, or source revision
vectors. It ranks the small project's lexical and vector candidates in memory;
no MySQL vector extension is required.

`await service.drain_indexing()` waits for outstanding derived indexing during
graceful shutdown. Current-source lexical search and graph reads remain available
before indexing finishes. A process killed after publication may leave missing
vectors; Markdown and replay receipts remain durable and lexical search works.
