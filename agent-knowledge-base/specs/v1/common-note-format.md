# Common note format — v1

The terms **must**, **required**, and **reject** describe publication rules.
Every type specification adds to this format. These rules specify Markdown
documents; they do not restore the previous entity/relationship ontology.

## File and body

- A note must be one UTF-8 `.md` file, without a byte-order mark, using LF line
  endings and a final newline.
- The file must begin with `---`, one YAML mapping, and a closing `---` delimiter.
  Reject duplicate keys, custom YAML tags, aliases, and multiple YAML documents.
- After frontmatter, the first nonblank line must be one H1 heading exactly
  matching `title`. No other H1 is allowed outside fenced code blocks.
- Required H2 sections must occur exactly once outside fenced code blocks. Each
  must contain meaningful content; state an honest limitation or `None observed`
  when appropriate. Empty sections, TODO-only placeholders, and invented facts
  do not satisfy a requirement. Additional H2/H3 sections are allowed.
- Filenames and folders must be descriptive. Use vault-relative POSIX paths;
  reject absolute paths, `.`/`..` components, backslashes, and control characters.
  Suggested folders are examples, not a fixed ontology or required directory tree.

## Required frontmatter

| Key | Type and rule |
| --- | --- |
| `spec_version` | Integer `1`. |
| `id` | Nonblank opaque string, unique within the project KB. Allocate UUIDv4 by default; preserve verified existing IDs. Never derive identity solely from title, path, or current content. |
| `type` | One type from the v1 index. |
| `title` | Nonblank single-line plain-text string; must match the H1. |
| `project_id` | Nonblank string matching the authenticated project's identity. This field cannot grant access. |
| `created_at` | Quoted RFC 3339 timestamp with timezone; time the note was first created. |
| `updated_at` | Quoted RFC 3339 timestamp with timezone, at or after `created_at`; last content/metadata update. |
| `status` | `active`, `archived`, or `superseded`. This describes note lifecycle, not whether an assertion is true or a task is complete. |

## Optional common frontmatter

| Key | Type and rule |
| --- | --- |
| `repository` | Quoted, unaliased wikilink to a repository note. Required by repository-scoped types; optional on finding/insight/decision/handoff/guide. Omit for project-wide knowledge. |
| `source_event_id` | Nonblank replay key supplied or persisted by the collector; required for merge/push occurrences. A retry must reuse it. It is distinct from an agent session ID. |
| `observed_at` | Quoted RFC 3339 timestamp for actual source observation, distinct from note creation and event occurrence. |
| `session_id` | Verified nonblank native agent-session identity, when available. Omit instead of guessing. |
| `tags` | List of nonblank tag strings, without leading `#`. |
| `aliases` | List of nonblank alternative title strings. |
| `superseded_by` | Quoted, unaliased wikilink to a replacement note; required when `status: superseded`. |

Only common keys and keys documented by the selected type are allowed in v1.
Optional values must be omitted when unavailable, not null or fabricated. Quote
timestamps, Git hashes, Git refs, paths with YAML punctuation, and all wikilinks.
Lists must contain distinct values. Required strings must not be whitespace-only.

## Links, scope, and sources

- Every note must have `## Related notes`. Include at least one internal link.
  Project notes link to repository notes; repository notes link to their project.
  Both can be created in one proposed batch.
- Internal note links use `[[Vault/Relative Note Path]]`, with optional display
  alias or heading, and omit `.md`. Paths are case-sensitive. Use full paths to
  avoid ambiguous duplicate titles. Metadata links have no alias or heading.
- Links must resolve inside the same project vault against published notes plus
  the proposed batch. Heading links must target existing headings. Broken links
  are not accepted publication placeholders. Do not link a note to itself.
- Standard Markdown links are allowed for external sources. Source-code paths
  are repository-relative paths in code spans, with repository identity and
  commit/ref context when known; they are not automatically KB wikilinks.
- Record observations as observations, intentions as intentions, and conclusions
  as interpretations. State unknowns explicitly in prose. Never claim a test,
  commit, merge, or push succeeded without evidence.
- A repository reused by two projects has independently scoped notes in each KB;
  a shared URL does not grant cross-project access or imply automatic syncing.

## Git identifiers and timestamps

Git object hashes belong in source-related notes. Use the complete observed
lowercase hexadecimal ID, quoted in YAML. Verify completeness against the source;
do not assume a fixed 40-character length or accept abbreviations. Missing Git
facts are omitted where optional, or leave a required observation pending.
Git author/committer timestamps must not be presented as hook occurrence times.

## Embeddings, revisions, and publication

- Do not put embedding vectors, model names, chunk vectors, similarity scores,
  or the note's own content hash into frontmatter or body. MySQL holds derived
  note/chunk search data keyed to stable note ID and published content revision.
- Indexing computes a content hash from the exact stored UTF-8 file bytes. Chunk
  entries also identify their source revision and heading/position. Model and
  dimension metadata live beside the vectors. Changing text invalidates stale
  index entries; delayed results attach only to the matching source revision.
- Revision counters, object keys, locks, request receipts, and indexing status
  are storage bookkeeping, not required note fields. Markdown remains the
  rebuildable knowledge source. Note/index publication across SeaweedFS and MySQL
  requires a separate recoverable storage protocol; these specs promise no
  cross-system transaction.
- Create/revise/archive notes through the project KB agent. Do not silently
  overwrite concurrent edits. Archive preserves ID/path/history and links;
  supersession links to the replacement. Archived/superseded notes remain valid
  link targets but should be excluded from default current-context search.
- A ref no longer being active is not sufficient reason to erase commit/merge
  history. Hard deletion and incoming-link repair require a separate policy.
  Direct Obsidian editing/sync behavior is not decided by this specification.

All note examples in the type specifications include these common fields.
