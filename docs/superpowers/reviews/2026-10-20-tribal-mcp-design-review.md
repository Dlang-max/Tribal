# Tribal MCP design review record

Proposal: [Tribal MCP Server Design Proposal](../specs/2026-10-20-tribal-mcp-design.md)  
Date: **2026-10-20**  
Requested process: write the proposal, review with a subagent, revise and repeat for at most three review rounds, stopping early if no improvements are identified.

This records design review, not implementation testing. The workspace is not a Git repository; there is no commit range to review.

## Round 1

Reviewer: `mcp_design_review_1`, read-only independent subagent.  
Result: **Three actionable findings; revised before round 2.**

| Finding | Severity | Disposition |
|---|---|---|
| Idempotency recovery ran after mutable-state validation, breaking retries of completed additions/edits. | High | Accepted. Section 7 now resolves stored keys before mutable preconditions, defines race recovery, and retains authorization checks. Acceptance criterion 4 explicitly covers completed operations and later document changes. |
| A lease could expire while application waited for database locks. | Medium | Accepted. Sections 8 and 10 define a final fenced authorization update using the database clock after all locks/writes, with rollback on expiry. Added a deadline field and lock-wait acceptance case. |
| Historical revision reads had no discovery mechanism. | Medium | Accepted. Added `list_document_revisions`, bounded pagination and deletion opt-in, plus an acceptance case for independent readers without proposal access. |

The reviewer accepted repository-wide generation invalidation as a deliberate conservative trade-off. Executable SQL validation, provider/SDK choice, semantic search, attachment synchronization, and per-change human approval were explicitly set aside as deferred validation or outside scope.

## Round 2

Reviewer: `mcp_design_review_2`, a fresh read-only subagent.  
Result: **Round 1 fixes confirmed; two additional actionable findings; revised before round 3.**

| Finding | Severity | Disposition |
|---|---|---|
| A late heartbeat could renew an already expired lease before reclamation. | Medium | Accepted. Section 8 now requires unexpired lease/deadline during renewal, caps extension at the fixed deadline, and forbids claim resurrection. Added a delayed-heartbeat acceptance case. |
| Exact-path lookup was promised without a callable path argument. | Medium | Accepted. `get_document` now accepts exactly one of UUID or exact current vault path. Defined case sensitivity, moves, repository boundaries, deletion opt-in, and revision ownership checks, with an acceptance case. |

The reviewer set aside executable DDL, deployment provider/SDK choices, optional enumeration of deleted documents, and broader search features as implementation validation or additional scope.

## Round 3

Reviewer: `mcp_design_review_3`, a fresh read-only subagent.  
Result: **Earlier fixes confirmed; three companion-spec alignment findings; incorporated in the final revision.**

The Markdown specification was updated during this design task. The third reviewer read the updated version and identified differences from the draft MCP proposal; its requirements were also reread before making the final changes.

| Finding | Severity | Disposition |
|---|---|---|
| Application locked the proposal before the repository, contrary to the updated publication protocol. | P2 | Accepted. Section 10 now begins by locking the repository row, then the proposal and document rows. Workflow-only cancellation/lease transactions cannot acquire the repository lock afterward. Added a lock-order acceptance case. |
| The design rejected occupied-path swaps, which the updated Markdown specification requires. | P2 | Accepted. Replaced rejection with transaction-local reserved-path staging. Removed `E_PATH_TRANSITION`; acceptance criteria now require successful swaps without committed temporary paths or extra revisions. |
| The design's 1 MiB file limit was below the current 8 MiB format capacity without identifying a restricted profile. | P3 | Accepted. Raised the document limit to 8 MiB and the aggregate decoded proposal limit to 64 MiB. Added transport/storage capacity requirements and the restricted-profile rule for deployments lowering capacity. Model-context limits remain separately reported as needs-evidence. |

Also made the full current-link refresh explicit, pinned Unicode portable comparison to the current specification, and documented the inherited immutable-chunk/embedding publication rules and committed-snapshot reads. These alignments do not add public tools or require optional semantic search.

The reviewer found no additional core authorization, recovery, idempotency, or public-tool gaps and set aside executable DDL, runtime proof, language/provider selection, and optional embeddings as implementation work or documented exclusions.

## Final review status

Completed the requested maximum of **three reviewer-subagent rounds** and incorporated all eight actionable findings. The third review required improvements; the final revisions received document consistency checks rather than a fourth subagent review. No clean-review verdict is claimed for the post-review revision, and no software has been implemented or runtime-tested.

Final verification checks local Markdown link targets, heading anchors, fenced-block pairing, required design sections, placeholder markers, and the presence/removal of the specific contracts changed by review. These checks validate the document artifact, not the future service.

## Subsequent scope correction: embeddings and semantic search

After the three review rounds, the user explicitly required embeddings and semantic search in v1. This supersedes the original draft's lexical-first scope and the earlier reviewers' treatment of embeddings as optional. The proposal now requires embedding profiles, durable generation/publication jobs, semantic retrieval by default, hybrid context retrieval for admission, observable indexing coverage/readiness, model-profile migration, and semantic acceptance cases.

The baseline retrieval backend computes exact cosine similarity in the application over eligible MySQL-stored vectors, without depending on MySQL Community Edition's unavailable `DISTANCE()` function. Performance must be benchmarked before deployment; a future indexed scorer can replace it without changing the public semantic-search contract. Lexical retrieval is an explicit supplemental mode, not a silent replacement for a failed semantic query.

This scope correction received document consistency checks. It was made after the requested three-round subagent review process and does not inherit a new subagent-review verdict.

## Subsequent scope clarification: knowledge spaces and available evidence

The user clarified that Tribal covers business processes and other organizational knowledge and cannot assume access to Git. The MCP design now uses knowledge spaces for API ownership, permissions, publication, and embedding configuration, with Git as an optional source alongside documents, conversations, tickets, observations, and operational records. Existing Markdown retains `repository` as a documented legacy envelope spelling for the knowledge-space key; storage renames and companion-spec alignment are explicit pending migrations, not claims that the older companion files have been rewritten.

The review workflow now distinguishes policy/intent, implementation behavior, observed practice, and attributed reports. Claim-level supported/contradicted/inconclusive assessments record accessible sources, authority, scope, freshness, and limits separately from admission and authored verification. A business-only example and acceptance cases cover no connectors, unavailable evidence, conflicting policy, source permissions, and unchanged round trips. Embeddings and semantic search remain required in v1.

This clarification received document consistency checks and no additional subagent-review round. Earlier review results remain a history of the versions reviewed, not a clean-review verdict for these subsequent changes.
