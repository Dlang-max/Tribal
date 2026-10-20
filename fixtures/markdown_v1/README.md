# Markdown v1 review-edge fixtures

These are synthetic design acceptance fixtures for the [Tribal Markdown v1 specification](../../tribal_markdown_spec.md) and [database schema](../../tribal_schema.md). They are not implementation test results. No MySQL importer, Obsidian integration, Mermaid renderer, or embedding provider has been exercised by creating this package.

## Layout

- `baseline/` is one complete six-document vault for knowledge base `fixture-kb`.
- `overlays/` contains selected replacement or new file contents. Its directory names are test-case organization, not their intended vault paths.
- `manifest.json` maps each fixture file to its canonical SHA-256 hash and each baseline vault path to a document ID/current revision. It defines selected writes and expected outcomes for independent scenarios.

Configure the knowledge base and domains `documentation`, `database`, `authentication`, and `botany` before loading the baseline. This configuration requires no Git repository, checkout, remote URL, or filesystem resource. Copy only `baseline/` into a working vault. The README, manifest, and overlay directory are not knowledge files to import recursively. Each scenario starts from a fresh baseline unless explicitly described otherwise.

The mock exported base tokens establish initial current revisions in an importer test harness. For a fresh database import, the actual service may allocate different revision IDs; the harness must substitute those actual tokens consistently before exercising update scenarios. Document IDs remain fixed. Revision token substitution must not change canonical hashes.

The `verified` procedure illustrates a complete verification assertion and explicitly declares its `git_repository` context, rather than assigning a repository to the knowledge base. Its evidence is fictional. No real test outcome or Git commit is claimed. Optional evidence-availability checks can produce warnings; the fixture does not require Git or execution of the illustrative command.

The botany finding uses an experiment context and an opaque notebook-page revision. The ordinary-folder code reference uses a `filesystem` context with an edition string instead of a Git hash. Other notes declare no context at all. The context-variant overlays show two Git repositories in one note, a context-free note in the same domain, and an unfamiliar context/source profile. No note inherits Git from its domain, knowledge base, neighboring notes, vault directory, or importing process.

## Scenario expectations

`writes[].file` names a file in this package. `writes[].path` is the logical destination path in the test vault or import request. A move is identified by its unchanged document UUID, not by treating an absent old path as deletion.

| Scenario | Expected behavior |
|---|---|
| `unchanged_reimport` | Six no-ops; no new authored revisions. |
| `transport_requote_and_move` | Token position/quoting changes only; canonical hash and revision stay unchanged. |
| `properties_style_metadata_edit` | One revision for the edited summary; verifier, UTC text, evidence, and link targets survive. This is a source fixture, not an actual UI test. |
| `stale_base_rejects_changed_file` | Reject with `E_REVISION_CONFLICT`; publish nothing. |
| `path_only_move` | One location revision; same document UUID and canonical hash. |
| `new_duplicate_refreshes_unchanged_source` | Create one new document; an unchanged procedure's bare `[[Setup]]` becomes ambiguous in the same commit. |
| `rename_with_companion_link_edits` | Move database setup and explicitly edit incoming links; publish both revisions and updated bindings atomically. |
| `swap_occupied_paths` | Swap root/nested guides through reserved transaction-local paths; one revision per move, no committed staging paths. Relative and qualified links resolve to the UUIDs now at those final paths. |
| `serialized_portable_collision` | Two separate creates compete for `Setup.md` and `setup.md`; with upper acquiring the lock first, upper commits and lower receives `E_PATH`. |
| `stale_embedding_after_rechunk` | Replace chunk 101 with fresh chunk 201; an old job for chunk 101 is discarded and never attached to 201. No authored revision is added. |
| `two_git_contexts_one_domain` | One new note selects two separately declared Git resources through source context keys. |
| `same_domain_without_git` | A general note in the authentication domain has no Git context and triggers no Git probing. |
| `unknown_context_and_source_types` | Preserve extensible profiles and disclose their unchecked type-specific semantics. |

An expected graph reference to `baseline_links` means the listed target UUIDs, anchors, and diagnostics. Entries in `binding_changes` override the corresponding source-document/ordinal binding; other occurrences retain their baseline target. A path-only source move also changes its returned source path, as specified by that scenario.

The `[[Guide]]` baseline occurrence intentionally has `W_LINK_AMBIGUOUS`: both root and nested guides exist. The adjacent relative Markdown link explicitly resolves to the root guide. Table alias escaping, a heading target, literal wiki-looking code, and a Mermaid diagram exercise rich-content boundaries. Neither example code nor diagram edges contribute graph occurrences.

`lexical_cases` specifies mixed-syntax precedence and malformed-link expectations. `lexical_search_cases` exercises literal lookup independently of MySQL full-text tokenization. `capacity_cases` gives generators rather than committing multi-megabyte files; a future validator harness supplies an otherwise valid envelope around each generated value. `context_cases` supplies positive examples and negative generators for explicit context membership, generic source versions, obsolete Git-root fields, and conditional Git-specific validation. `source_resolution_cases` provides expected directory-root URI resolution and Git repository/path/version tuples. A selected Git context controls revision syntax even for a publication or dataset; editions and release labels then belong in source details.

The manifest's baseline occurrence list is an expected oracle, not output from an implemented Tribal parser. Fixture-integrity verification checks source metadata, referenced headings, file hashes, and declared data relationships; it does not substitute for testing the future parser, importer, or worker lifecycle.

## Canonical hashes

For each file, normalize line endings to LF, ensure a final newline, and remove exactly the one complete physical line containing the parsed top-level `tribal_base_revision` entry. Preserve every other byte. SHA-256 of the result must equal `files[relative_path].canonical_sha256`.

The token-only overlay has the same canonical hash as its baseline. The summary-edit overlay differs. Path-only moves use the same canonical source bytes as their baseline documents. All files are UTF-8.

## Actual Obsidian Properties compatibility procedure

This procedure remains **unexecuted**. An implementation must record its tested Obsidian version before claiming compatibility.

1. Copy the baseline into a clean working vault and retain a separate original copy. Configure Text for UUIDs, `verified_at`, and `tribal_base_revision`; Number for `schema_version`; and the documented List/Tags types where relevant. Edit structured `contexts`, `scope`, and `sources` in Source mode; do not add Git metadata to notes that do not declare Git work.
2. Open `authentication/Startup.md` in Properties. Change its summary, then save. Do not change the verifier timestamp or remove the base token. Edit nested evidence only through Source mode.
3. Inspect the saved source. Confirm the timestamp remains `2026-10-20T12:00:00Z`, source details remain present, and the base token's parsed UUID is unchanged. Different token position or scalar quoting is allowed.
4. Import with the retained current base. Expect exactly one revision, preserved verifier/evidence, unchanged link targets, and a canonical hash calculated from the actual saved bytes. The supplied properties-style overlay is illustrative; actual UI formatting need not match its hash.
5. Separately move/requote only the transport entry in Source mode. Reimport and expect no authored revision.
6. Open the root and nested guide references, the aliased table link, and the Mermaid diagram in Reading view. Record rendering and link-navigation results. Mixed syntax from `lexical_cases` must be tested separately before claiming renderer equivalence to Tribal precedence rules.
7. Export and reimport the unchanged saved vault. Expect no new revisions and preserved canonical authored bytes. Record any unsupported feature or rendering warning rather than treating an unchecked feature as passed.

## Running implementation acceptance checks

A future importer harness should load a fresh baseline per scenario, apply the exact selected writes, and compare revision counts, UUIDs, canonical hashes, diagnostics, and graph occurrences. Concurrency cases require overlapping real transactions; running them sequentially as ordinary file validation is insufficient. The stale-worker scenario requires delaying an old result until after replacement commits. Path swaps must also assert that no staging path survives rollback or commit.

These checks should run against the declared MySQL and Obsidian versions once those integrations exist. No application implementation is included in this package.
