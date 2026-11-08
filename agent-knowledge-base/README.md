# Agent knowledge base

Tribal stores one Markdown knowledge base per project. A project may contain
multiple repositories. Agents use the project's authenticated MCP server; the
knowledge-base agent retrieves context and reviews requested additions,
revisions, links, and removals.

Markdown files in SeaweedFS are the knowledge source. MySQL holds the searchable
catalog, text index, note/chunk embeddings, and processing metadata. Embeddings
are derived data and do not belong in Markdown notes.

The [v1 specifications](specs/v1/README.md) define valid note documents. The
[v1 validator](validation/v1/README.md) checks their structural and local cross-note
rules. Storage adapters, indexing, hooks, and the updater agent remain separate
work. The Markdown specifications replace the removed `ontology/` assets.

The [v1 MCP interface](mcp-interface-v1.md) defines two proposed public tools:
`seed_agent_context` for retrieval and `update_knowledge_base` for submissions.
It is an interface specification, not a runtime implementation.

The documented v1 defaults are practical specification choices made for these requests;
they do not imply that every storage, synchronization, or MCP detail is settled.
