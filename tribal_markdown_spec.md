# Tribal Markdown Specification v1

Version: **1**  
Status: **Draft for review**  
Date: **2026-10-20**

This document defines the files AI agents and humans write to contribute knowledge to Tribal. It specifies the document envelope, supported content, evidence, links, validation, and preservation rules. It does not implement a validator or change the database schema.

The words **MUST**, **MUST NOT**, **SHOULD**, **SHOULD NOT**, and **MAY** express requirements. MUST requirements determine conformance. SHOULD requirements are recommendations whose violation produces a warning rather than rejection.

## 1. Goals and boundaries

A Tribal document MUST be readable as a normal Markdown file and usable without a Tribal-specific Obsidian plugin. Both a small finding and a substantial maintained overview are first-class documents.

Tribal is domain agnostic. A **knowledge base** is a named knowledge collection; a **domain** is a subject area within it; a note's **contexts** identify the external resources or situations involved in its work. None of these concepts implies software development or Git. Research, operations, history, creative work, and software engineering use the same core document format.

The format provides:

- Stable document identity independent of filenames and titles.
- Metadata that agents can validate and query.
- A flexible body supporting diagrams, tables, code, and prose.
- Explicit evidence and applicability without requiring identical sections in every document.
- Deterministic internal references and preservation through import/export.
- Enough structural information to retrieve passages without corrupting rich content.

V1 does not define automatic knowledge consolidation, executable notebooks, attachment synchronization, real-time file synchronization, or automatic proof that a claim is correct.

For the v1 vault interchange profile, one vault represents one knowledge base. Cross-domain links are supported. A combined vault spanning knowledge bases and cross-knowledge-base wikilink resolution are outside this profile; separate vaults MAY be managed by the same Tribal instance. A vault is an interchange representation, not a requirement that notes originate in a local filesystem or Git checkout.

This specification and ordinary project documentation are not themselves required to be Tribal knowledge documents.

## 2. File envelope and canonical representation

A document MUST have:

1. A filename ending in lowercase `.md`.
2. UTF-8 content without a byte-order mark or NUL characters.
3. YAML frontmatter beginning on the first line with exactly `---`.
4. A closing frontmatter delimiter consisting of exactly `---` on its own line.
5. A nonempty Markdown body containing at least one non-whitespace text character, including text inside a table, list, or code block.

Writers MUST emit LF line endings and a final newline. Importers MUST normalize CRLF or CR line endings to LF and append a final newline if absent. These are the only automatic content normalizations permitted by core v1.

Importers MUST NOT silently reformat YAML, reorder properties, reflow paragraphs, renumber lists, normalize Unicode, or rewrite code and diagram source. Blank lines, comments, quoting, and unknown metadata MUST otherwise be preserved.

The canonical authored document is the normalized complete file, including frontmatter, with the generated transport property from Section 11 removed if present. `content_hash` is SHA-256 over its exact UTF-8 bytes. Derived chunk offsets refer to these bytes, with zero-based half-open ranges `[start_byte, end_byte)`.

### 2.1 Storage-aligned limits

The following are acceptance limits, not style recommendations. Byte limits count the UTF-8 representation after decoding YAML or link escapes as applicable, except that `raw_link` counts its exact original source bytes. Character limits count Unicode code points. Exceeding a limit MUST produce `E_LIMIT` before any database write. Implementations MUST NOT silently truncate accepted content or its projections.

| Value | Maximum |
|---|---|
| Complete canonical authored file | 8,388,608 bytes (8 MiB), including frontmatter and final newline. |
| Decoded `summary` | 8,192 bytes. |
| Decoded source or context `locator` | 8,192 bytes. |
| One recorded internal link's original `raw_link` | 16,384 bytes. |
| Parsed internal link `target_text` | 1,024 code points. |
| Parsed heading anchor or root-level heading's extracted plain text | 255 code points. |
| File path | 512 code points, as further restricted in Section 7.1. |

The file-size check excludes the generated transport line. The normalized imported representation MAY exceed 8 MiB only by the byte length of that one transport line, which MUST NOT exceed 256 bytes. The transport line is validated before its removal.

The file cap ensures any intact source chunk fits `MEDIUMTEXT`; summary, locator, and raw-link caps fit `TEXT`. The target and anchor caps match their `VARCHAR` projections. YAML collections and source details remain subject to the overall file cap. Deployments MUST configure client/server packet sizes to carry the accepted representation and derived JSON, use strict SQL mode, and report operational capacity failures separately from format errors. They MUST NOT advertise full v1 ingestion if their configured capacity is lower. See [MySQL string capacities](https://dev.mysql.com/doc/refman/9.7/en/string-type-syntax.html).

## 3. Frontmatter

### 3.1 Parsing rules

Frontmatter MUST be a YAML 1.2 block mapping with string keys. Duplicate keys at any nesting level, custom YAML tags, anchors, aliases, and merge keys are prohibited. Values MUST be representable using JSON-compatible strings, numbers, booleans, nulls, arrays, and mappings; nonfinite numbers are prohibited.

Field types are strict. For example, `schema_version: "1"` is invalid because it is a string, and `tags: authentication` is invalid because tags must be a list. There is no implicit scalar-to-list or string-to-number coercion.

Ordinary scalar Tribal metadata is flat so it can be edited using Obsidian's Properties panel. Structured `contexts`, `scope`, and `sources` use Source mode. Obsidian currently documents nested properties as unsupported in its built-in property editor; this does not prevent source editing of the file. See [Obsidian Properties](https://obsidian.md/help/properties).

### 3.2 Required fields

| Field | Type | Requirements |
|---|---|---|
| `schema_version` | Integer | MUST equal `1`. |
| `id` | String | Canonical lowercase UUID in `8-4-4-4-12` hexadecimal form; MUST NOT be the nil UUID. Generated before the file is first submitted and preserved thereafter. |
| `title` | String | Nonblank, single line, at most 255 Unicode code points. |
| `knowledge_base` | String | Knowledge base key, at most 128 characters, matching the key syntax below. |
| `domain` | String | Domain key within the knowledge base, at most 128 characters, matching the key syntax below. |
| `kind` | String | One of `finding`, `overview`, `decision`, `procedure`, `reference`. |
| `summary` | String | Nonblank plain text summarizing what a reader can learn. Folded YAML strings are allowed. No wikilinks, images, or executable content are interpreted in this field. |

Knowledge base and domain keys MUST match `[a-z][a-z0-9]*(?:[-_][a-z0-9]+)*`. Importers MUST reject unknown knowledge base/domain assignments unless the caller explicitly supplies a configuration that creates or maps them. Importers MUST NOT infer a new domain from a misspelled key.

The UUID format does not mandate a particular UUID generation version. An existing document MUST NOT receive a new ID merely because its title, path, or domain changes. A copied document intended to become independent MUST receive a new ID.

Summaries SHOULD consist of one to three concise sentences. Sentence-count recommendations are warnings; the byte limit in Section 2.1 is mandatory.

### 3.3 Optional fields and defaults

Defaults apply to interpreted metadata; importers MUST NOT insert omitted defaults into the authored text merely to materialize them.

| Field | Type | Default / requirements |
|---|---|---|
| `status` | String | `active`; one of `active`, `superseded`, `archived`. |
| `tags` | List of strings | `[]`; unique, nonblank Obsidian-compatible tag names without a leading `#`. |
| `aliases` | List of strings | `[]`; unique, nonblank alternative display names. |
| `contexts` | List of mappings | `[]`, meaning no working context was declared; follows Section 3.6. |
| `scope` | Mapping | `{}`; domain-specific applicability such as population, region, date range, conditions, or operating environment. Keys and JSON-compatible values are author-defined and preserved. |
| `verification_state` | String | `unverified`; one of `unverified`, `verified`, `disputed`. |
| `verified_at` | String | Absent by default; UTC timestamp in `YYYY-MM-DDTHH:MM:SSZ` form when present. Writers SHOULD quote it; semantic string typing and the UTC suffix are mandatory. |
| `verified_by` | String | Absent by default; a nonblank verifier identifier of at most 255 characters when present. |
| `sources` | List of mappings | `[]`; follows Section 5. |
| `cssclasses` | List of strings | Optional Obsidian presentation metadata; not interpreted as knowledge classification. |

Null MUST NOT be used in place of an optional field's declared type; omit that field instead. Arbitrary values inside `scope` and context/source `details` may contain JSON nulls. Missing scope means applicability is unspecified, not that the claim is universally valid.

Tag names may contain Unicode letters and digits, `_`, `-`, and `/`, MUST contain at least one nondigit character, and MUST NOT contain whitespace. For portable authoring, tags SHOULD use lowercase names such as `authentication` or `database/startup`.

Unknown top-level properties MUST be preserved and produce `W_UNKNOWN_PROPERTY`; they MUST NOT silently become Tribal metadata. Properties beginning with `x_` are designated user extensions and do not produce that warning. The `tribal_` prefix is reserved: unrecognized properties with that prefix MUST be rejected. The one v1 transport property is defined in Section 11.

The earlier draft's `repository`, `scope_branch`, `scope_commit`, and `scope_environments` properties are obsolete and MUST produce `E_CONTEXT` rather than silently imply a Git context. Authors must assign a neutral `knowledge_base` and explicitly migrate relevant working-context/applicability data. A repository identity MUST NOT be automatically treated as a knowledge-base identity.

### 3.4 Lifecycle and scope semantics

- `active` means the document is eligible to guide current work, subject to scope and verification.
- `superseded` means newer knowledge replaces it. The body SHOULD link to its replacement.
- `archived` means the document is retained for history and normally excluded from current guidance.
- `unverified` means the asserted knowledge has not been verified under this contract.
- `verified` records a scoped assertion of verification; it does not mean Tribal independently executed a test or proved the prose true.
- `disputed` means material claims are contested. The body SHOULD explain the disagreement and relevant evidence.

A `verified` document MUST include `verified_at`, `verified_by`, and at least one source. Its author MUST supply evidence adequate for its material claims; this semantic requirement cannot be established from metadata alone.

An external resource version is observation context, not a guarantee that knowledge applies to later versions. A later source edition, dataset release, or Git commit MUST NOT, by itself, cause the importer to label a document false or stale. Authors SHOULD explain applicability limits in the body. Tribal document revisions and SQL transaction commits are service concepts independent of any external version-control system.

### 3.5 Obsidian property-editing profile

Vaults using the Properties panel SHOULD configure `schema_version` as Number; `tags` as Tags; `aliases` and `cssclasses` as List; and other ordinary scalar fields, including UUIDs, `verified_at`, and `tribal_base_revision`, as Text. In particular, `verified_at` MUST NOT rely on Obsidian's native Date & time type to retain the required explicit UTC suffix. `contexts`, `scope`, and `sources` use Source mode.

Property order and YAML string quoting are presentation choices. Moving or requoting the transport entry alone MUST NOT create a revision or invalidate its token. Editing other frontmatter formatting is an authored byte change, accepted with a current base token, and MUST NOT be mistaken for an unchanged canonical file. Exporters preserve that edited source rather than reverting to their preferred style.

An implementation claiming tested Properties-panel compatibility MUST record the Obsidian version and pass the manual edit/reimport procedure in the fixture package referenced in Section 14. This specification does not claim that the current documents have been tested in Obsidian.

### 3.6 Explicit working contexts

Each `contexts` entry declares one working context. Contexts belong to a particular document revision, not to the knowledge base or domain by default. A note MAY declare zero, one, or several contexts; notes in the same domain may work with different resources. A linked note's context MUST NOT be inherited implicitly.

| Field | Type | Requirements |
|---|---|---|
| `key` | String | Required, at most 128 characters; uses the domain-key syntax and is unique within the note. Sources refer to this key. |
| `type` | String | Required, at most 64 characters; uses the domain-key syntax. The vocabulary is open, e.g. `git_repository`, `filesystem`, `dataset`, `experiment`, `organization`, or `interview`. |
| `locator` | String | Optional nonblank resource/situation identifier, at most 8,192 UTF-8 bytes. Required for the `git_repository` and `filesystem` profiles. |
| `label` | String | Optional nonblank human-readable name. |
| `details` | Mapping | Optional JSON-compatible type-specific facts. |

Unknown entry fields are rejected unless prefixed with `x_`; arbitrary facts belong in `details`. Unknown context types are valid under the common shape; the importer preserves them without guessing their semantics. It MUST disclose type-specific checks it did not perform. Locators may be URIs, external identifiers, or explicit local resource roots. They MUST NOT be defaulted from the importing process's current directory or vault path.

**Git profile:** If a note records work performed in a Git repository, its author MUST declare a context with `type: git_repository` and an explicit `locator` identifying that repository. A known branch MAY be recorded as nonblank `details.branch`; a known commit MAY be recorded as `details.commit`, a complete lowercase 40- or 64-character hexadecimal object ID. Unknown branch/commit values are omitted, not fabricated. An absolute local root is valid when no remote URL exists. Multiple Git repositories require separate context keys. The core format neither requires Git nor infers its presence from filenames, a domain name, or the service's checkout. Authors are responsible for truthful context declarations; format validation cannot establish that work occurred in Git by inspecting prose or probing the importing service's environment.

**Filesystem profile:** `type: filesystem` declares a directory root without implying version control. Notes about ordinary folders and files do not need a Git context. The locator MUST be an absolute local path or an absolute hierarchical URI with a path and without a query or fragment. Relative roots such as `.`, `../notes`, and `notes/` are invalid; a process working directory is never supplied implicitly. Absolute local paths may use their declared platform's syntax; authors SHOULD use `file:` URIs for portable interchange.

The root denotes a directory even when its locator has no trailing slash. Relative file/code source locators MUST be POSIX paths with no empty, `.` or `..` segments and no leading slash, query, or fragment. For URI roots, append the path segments to the complete root path with one boundary slash, percent-encoding source path characters as path data; do not use ordinary document-base URI joining that would replace the root's last segment. For local roots, append beneath that directory using the root platform's separators. The source MUST NOT escape the declared root. An absolute source URI is already self-contained and is not appended; any declared context still controls revision interpretation.

For example, `file:///srv/unversioned-service` plus `config/auth.json` resolves to `file:///srv/unversioned-service/config/auth.json`, exactly as it would if the root had a trailing slash. By contrast, a Git locator identifies a repository tree, not a web page directory: preserve the tuple of repository locator, repository-root-relative path, and effective Git revision. Do not append source paths to a remote `.git` URL as though it were an HTTP file base. Git locators MUST be absolute URIs, absolute local roots, or explicit SCP-style remote locators such as `user@host:path`; relative checkout roots are invalid.

When a relative source locator needs a root, its source MUST select a declared context that supplies that root. Core relative file/code sources require the Git or filesystem profile; an implementation MAY advertise additional root-aware profiles with explicit validation rules. Unrecognized context and source types remain opaque under the common shape rather than being resolved against the vault. Missing context references, invalid known-profile fields, or relative file/code locators without a supported explicit root produce `E_CONTEXT`.

For example, Git facts appear only under an explicit context:

```yaml
contexts:
  - key: application-source
    type: git_repository
    locator: "https://example.org/example-service.git"
    details:
      branch: main
      commit: "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
```

The `scope` mapping describes applicability independently, such as `population`, `region`, `time_period`, or `conditions`. Contexts identify what was worked with; scope describes where the knowledge applies. Neither is an access-control boundary.

## 4. Document body and kinds

The body uses [GitHub Flavored Markdown 0.29-gfm](https://github.github.com/gfm/) as its baseline, with the explicit Tribal and Obsidian extensions below. Where rules differ, this specification takes precedence for Tribal processing.

Document kind describes purpose, not size. V1 does not require a universal set of headings or a fixed section order. A document MAY contain original explanations, supporting observations, and links to other documents regardless of its kind.

| Kind | Intended purpose | Recommended sections |
|---|---|---|
| `finding` | Record an observed behavior, constraint, dependency, or debugging discovery. | Claim; Evidence; Applicability. |
| `overview` | Explain a subject, process, or system and how its parts connect. | Background; Main concepts; Relationships; Known limitations. |
| `decision` | Explain a choice and its rationale. | Context; Decision; Alternatives; Consequences. |
| `procedure` | Explain a repeatable task. | Preconditions; Steps; Validation; Recovery. |
| `reference` | Maintain facts or lookup information. | Organization appropriate to the material, such as terminology, measurements, configuration, or comparison tables. |

These are templates, not required English headings. Authors MAY use other languages or structures. Validators MUST NOT reject an overview because it lacks a `Claim` heading, or a short finding because it has no headings.

A single `#` title heading matching `title` is RECOMMENDED but optional. Additional headings SHOULD form a meaningful hierarchy. Multiple title headings, skipped heading levels, and a title-heading mismatch SHOULD produce style warnings, not errors.

## 5. Evidence and provenance

`sources` contains machine-readable evidence references. Each entry has the following shape:

| Field | Type | Requirements |
|---|---|---|
| `type` | String | Required, at most 64 characters using the domain-key syntax; extensible classification with the conventions below. |
| `locator` | String | Required, nonblank; interpretation depends on `type`. |
| `section` | String | Optional; exact unique heading text within the current document, at most 255 code points. Omit for whole-document evidence. |
| `context` | String | Optional; exact `contexts[].key` identifying this evidence's working context, at most 128 characters. Must exist in this note when supplied. |
| `revision` | String | Optional nonblank source-version identifier, at most 255 code points. May identify an edition, dataset release, notebook entry, or Git object ID according to its declared context. |
| `details` | Mapping | Optional JSON-compatible source-specific information. |

Unknown source-entry fields MUST be rejected unless prefixed with `x_`; arbitrary source-specific data belongs in `details`.

| Source type | Locator convention |
|---|---|
| `file` | Self-contained absolute URI, or path relative to an explicitly selected filesystem/Git context; no implicit vault or process root. |
| `observation` | Observation record, field notebook, or event identifier; method and conditions SHOULD be described in `details`. |
| `experiment` | Experiment or trial record identifier; method and results SHOULD be described in `details`. No command execution is required. |
| `dataset` | Dataset identifier, URI, or DOI; `revision` can identify a release. |
| `publication` | Publication identifier, URI, DOI, or catalogue reference; edition/page information MAY appear in `revision` or `details`. |
| `interview` | Interview/recording/transcript identifier, with relevant provenance in `details`. |
| `code` | Self-contained absolute URI, or path relative to a selected Git/filesystem context; symbols or line ranges MAY appear in `details`. Code files need not be version-controlled. |
| `test` | Test record, file, or suite identifier; nonblank `details.outcome` is required. A `details.command` is optional and MUST be nonblank when present; a test is not assumed to be a software command. |
| `issue` | Absolute HTTP(S) issue or discussion URL. |
| `document` | Canonical Tribal document UUID; an optional `revision` pins a canonical UUID Tribal revision rather than floating to current content. `context` MUST be omitted because this references Tribal's own identity space. |
| `web` | Absolute HTTP(S) URL. |
| `other` | Nonblank locator whose meaning is explained in `details`. |

Source types are not a closed enum. An unfamiliar type with a valid common shape is preserved; optional type-specific validation is disclosed as unchecked. No domain must use code, tests, issues, or publications to record knowledge.

The selected context controls the revision namespace regardless of source type. When a source selects a `git_repository` context, its optional `revision` MUST be a full lowercase 40- or 64-character hexadecimal Git object ID and overrides that context's `details.commit`. When neither is present, the Git revision is unspecified. This also applies to an experiment, dataset, or publication explicitly stored in Git: put a human edition, trial entry, or dataset-release label in `details` when `revision` identifies its Git content.

Without a Git context, source versions are opaque strings subject only to the common limits, except that internal `document` sources require a UUID revision and omit context. Git hash checks MUST NOT be imposed solely because a source type is `code`, a domain concerns software, or a neighboring note uses Git. A publication with `revision: second-edition` and no Git context is valid; the same revision paired with an explicit Git context is `E_SOURCE`. The earlier draft's source `commit` field is not part of the v1 shape.

If `details.line_start` or `details.line_end` is supplied, both MUST be positive integers with `line_end >= line_start`. These are inclusive source-file line numbers. A source section MUST resolve to exactly one heading; a missing or ambiguous source section is an error because it would misattribute evidence. Referenced headings MUST have plain-text inline content, without inline markup, so this matching rule is unambiguous.

Sources do not require executing commands, running Git, mounting a dataset, or contacting remote services during import. Unavailable resource versions, missing local files, and inaccessible URLs SHOULD be reported when checked, but availability alone does not determine file-format validity.

Evidence metadata does not replace readable reasoning. The body SHOULD explain what was observed and how it supports the relevant claim. A test source with `outcome: failed` can be valid evidence of a failure; it is not automatically evidence of a fix.

For attribution, the importing service records its actual caller in database revision authorship. A file's custom author or verifier text MUST NOT be treated as authenticated caller identity.

## 6. Supported rich content

### 6.1 Core content

Implementations MUST preserve and structurally recognize:

- Paragraphs, headings, emphasis, strong emphasis, and strikethrough.
- Ordered and unordered lists, nested lists, and task lists.
- Blockquotes, thematic breaks, and inline code.
- GFM tables.
- Fenced code blocks, including backtick and tilde fences.
- Standard Markdown links and images.
- Tribal wikilinks and Mermaid fences as specified below.

An explicitly closed fence is required even though some Markdown parsers accept an implicit close at end of file. Authors SHOULD supply a language identifier such as `python`, `sql`, `bash`, `json`, or `text` for ordinary code blocks. Unknown identifiers are preserved as code, not rejected.

Importers MUST NOT execute code blocks. Inline code and ordinary code-block contents are literal: apparent headings, frontmatter, and links inside them MUST NOT be extracted as document structure or knowledge links.

### 6.2 Tables

Tables MUST use GFM pipe-table syntax with a header and delimiter row. Pipe characters within a cell MUST be escaped according to the Markdown table syntax, including the alias separator in a wikilink:

```markdown
| Component | Reference |
|---|---|
| Database | [[database/Connection lifecycle\|Connection lifecycle]] |
```

Importers MUST preserve table rows, cell contents, alignments, and escaped characters. Tables SHOULD have a nearby heading or explanatory paragraph to make their meaning clear when retrieved.

### 6.3 Mermaid diagrams

A fenced code block whose first info-string word is exactly `mermaid` is a diagram:

````markdown
```mermaid
flowchart LR
    Database[Initialize database] --> Auth[Initialize authentication]
    Auth --> Ready[Accept requests]
```
````

Diagram source MUST be preserved verbatim after file-level newline normalization. Import/export MUST NOT replace it with a rendered image.

Tribal renderers MUST support basic `flowchart` and `sequenceDiagram` diagrams and MUST publish the exact Mermaid version they use. Additional diagram types MAY be supported. An unsupported diagram type or a diagram parse failure MUST produce a warning and a readable source fallback rather than loss of the authored document. Ingestion-only implementations are not required to render diagrams and MUST report diagram syntax as unchecked when no Mermaid parser was used.

Authors SHOULD provide an adjacent prose explanation. Diagrams are content: node names, edges, click handlers, and apparent wikilinks inside Mermaid source MUST NOT create Tribal relationships. Authors MUST add ordinary document links outside the diagram when they intend graph relationships. Code and diagrams MUST NOT trigger application actions during import or rendering.

The syntax reference is the [Mermaid documentation](https://mermaid.js.org/intro/). Rendering can vary between Mermaid releases and editors; preserved source and documented renderer capabilities are the interoperability contract, not pixel-identical diagrams.

### 6.4 Additional Obsidian syntax

Footnotes, callouts such as `> [!note]`, highlights, math, block references, Obsidian comments, and note/attachment embeds MAY appear. Core v1 MUST preserve their source. Advanced rendering, transclusion, and semantic indexing of these extensions are not required.

Calls to plugins, Dataview-style queries, raw HTML, and embedded scripts MUST NOT be evaluated as Tribal processing. Unsupported constructs MUST remain available as authored source; implementations SHOULD report features they cannot render or interpret.

For predictable v1 behavior, authors SHOULD use ordinary wikilinks for relationships and Mermaid for diagrams. They SHOULD NOT place essential applicability or evidence only in collapsed callouts, hidden comments, or transcluded notes.

Opaque extension regions, such as math blocks, HTML blocks, comments, and embed syntax, MUST NOT produce speculative graph edges. An implementation that does not recognize a region well enough to extract links correctly MUST preserve it and report semantic extraction as unsupported for that region.

## 7. Identity, paths, and links

### 7.1 Vault paths

A document's location is its vault-root-relative POSIX path, including `.md`, not its identity. Paths MUST be at most 512 Unicode code points, MUST NOT be absolute, and MUST NOT contain NUL, backslashes, `.` or `..` segments. Empty path segments are prohibited. Names containing `#`, `|`, `[` or `]` are prohibited in v1 knowledge-document paths to avoid ambiguity with wikilink syntax.

Path segments MUST NOT start or end with whitespace. The root prefix `.tribal-staging/` is reserved for transaction-local path swaps and MUST NOT occur in authored or exported paths. Soft-deleted documents retain their path reservations, including portable-collision reservations, until explicitly purged or deliberately moved through a service operation.

The vault interchange profile MUST reject duplicate document IDs and paths. It MUST also reject paths that collide after Unicode NFC normalization and case folding, even if the host filesystem is case-sensitive. This comparison does not rewrite stored paths or content. Authors SHOULD avoid platform-specific reserved filenames and characters.

Portable comparison is `NFC(casefold(NFC(path)))` using Unicode 15.1 normalization and full default case folding, without locale-specific tailoring. Implementations MUST use the same Unicode tables or demonstrate equivalent comparison results. Original path spelling remains unchanged. Database collations are not substitutes for this check. All path-affecting operations MUST apply it under the knowledge base lock in Section 11.4, including concurrent creates, restores, moves, and case-only renames. The document being moved is excluded from comparison with its own old reservation.

The importer MUST verify that all imported knowledge documents declare the configured knowledge base. Subdirectories do not automatically establish domains; the `domain` property is authoritative.

Vault configuration directories such as `.obsidian` are not knowledge documents. Other `.md` files MUST be selected explicitly as knowledge files or diagnosed when they lack the required frontmatter; they MUST NOT be silently converted into conforming documents.

### 7.2 Wikilink forms

#### 7.2.1 Lexical rules and precedence

Block structure and literal/opaque regions are recognized first. Within eligible inline content, scan left to right. At an unescaped `[[`, try the wikilink rule before the GFM bracket-link rule. At other positions, a complete standard Markdown link or image consumes its entire source span; do not extract nested wikilinks from its label or destination. An unescaped `![[...]]` is an opaque embed, not a wikilink edge.

The core grammar is:

```text
wikilink := "[[" target [ "#" anchor ] [ "|" label ] "]]"
```

`target` is a path or filename stem and may be empty only when a nonempty anchor supplies a same-document reference. `anchor` and `label`, when present, MUST be nonempty. The first `#` before the alias separator starts the anchor; a further `#` is an unsupported nested-heading extension rather than a second target. The alias separator occurs at most once. Components MUST NOT have leading/trailing whitespace, newlines, control characters, literal square brackets, or backslashes. Spaces within names and labels are allowed. Wikilink components are literal text; percent escapes and inline emphasis are not decoded within them.

An opening delimiter is escaped when its first `[` is immediately preceded by an odd-length run of backslashes; ordinary GFM escape handling applies and no wikilink starts there. An even-length run leaves the delimiter eligible. In a table cell, GFM's source escape `\|` MUST first be recognized as the wiki alias separator without terminating the cell; that source escape is permitted as the one exception to the component backslash restriction. A literal pipe in a target is never supported.

The first `]]` on the same line closes a candidate. A candidate with invalid components, repeated alias separators, or no same-line close is literal source and produces `W_WIKILINK_SYNTAX`; its span MUST NOT be reinterpreted as nested internal links. For an unclosed candidate, that span ends at the line ending. A well-formed candidate exceeding a Section 2.1 projection limit instead produces `E_LIMIT`. The original source span, including table escapes, determines `raw_link` and occurrence offsets.

| Inline input | Required interpretation |
|---|---|
| `[[Target]]` | One wikilink occurrence. |
| `[[Target]](https://example.com)` | One wikilink followed by literal parenthesized text; not an external Markdown link. |
| `[Outer [[Target]]](https://example.com)` | One external Markdown link; no internal wikilink from its label. |
| `\[[Target]]` | Escaped opening; no wikilink occurrence. |
| `[[ Target ]]` | Literal malformed candidate and `W_WIKILINK_SYNTAX`; do not trim to a target. |
| `[[Target|one|two]]` | Literal malformed candidate and `W_WIKILINK_SYNTAX`. |
| `[[Target` | Literal malformed candidate to end of line and `W_WIKILINK_SYNTAX`. |
| `![[Target]]` | Preserved embed; no core graph edge. |

These precedence rules are normative Tribal behavior. Renderers integrating an existing Markdown engine MUST install equivalent inline rules; treating all wikilinks as a regular-expression postprocess over rendered text is not conforming. Obsidian rendering of mixed ambiguous syntax is a compatibility test, not assumed equivalence.

#### 7.2.2 Target resolution

The following forms are part of core v1:

```text
[[database/Connection lifecycle]]
[[database/Connection lifecycle.md]]
[[database/Connection lifecycle|Database connections]]
[[database/Connection lifecycle#Initialization]]
[[#Startup sequence]]
```

Wikilinks with `/` in the target MUST use vault-root-relative paths. A terminal `.md` is optional. A target without `/` resolves only if exactly one knowledge document has that filename stem across the vault. It MUST remain ambiguous if there are multiple candidates; Tribal MUST NOT guess based on a similar title, domain, or content.

When a root-level document shares its filename with a nested document, v1 does not invent a new wikilink root marker. Authors MUST use a relative Markdown link to select that root document unambiguously: `[Root guide](Guide.md)` from another root-level document, or `[Root guide](../Guide.md)` from a document one directory below the root. Thus `Guide.md` and `database/Guide.md` are both addressable even though `[[Guide]]` is ambiguous. A nested target remains addressable as `[[database/Guide]]`.

`title` and `aliases` are descriptive metadata, not alternate document identities or automatically resolved path targets. Authors SHOULD use a path plus a display alias instead of relying on a title being a filename.

Matching is case-sensitive and requires the exact spelling of the stored path. References with incorrect case MUST NOT be silently rebound. Path-qualified links are RECOMMENDED for cross-domain references and required to disambiguate repeated filenames.

Heading references use the exact plain-text heading content, excluding the heading marker and surrounding whitespace, rather than an invented slug. Referenced headings MUST contain plain text without inline markup. A heading target MUST resolve to exactly one heading in the target document. Duplicate headings are permitted, but references to them remain ambiguous. The core heading-anchor length limit is 255 code points.

Nested heading-path syntax and block-ID targets such as `#^block-id` are preserved extensions outside core heading resolution. Implementations MUST report them as unsupported rather than silently resolving them as ordinary headings.

### 7.3 Standard links and extraction

Relative Markdown links ending in `.md`, including reference-style Markdown links, MAY link to knowledge documents. Their paths are resolved relative to the containing file, with percent escapes decoded once. `.` and `..` segments in link destinations are normalized for lookup, but a reference escaping the vault root is unresolved and MUST NOT be followed. An optional fragment follows the same exact-heading rule after percent decoding.

An empty-path fragment such as `[Startup](#Startup%20sequence)` refers to the current document. Absolute HTTP(S) URLs and links to code or other non-Markdown files are preserved but are not internal knowledge-graph edges. Standard Markdown images are not document-link edges.

Only parsed internal links in ordinary body content create `document_links` records. Links in table cells and blockquotes count; apparent links inside inline code, code fences, Mermaid, comments, or other opaque regions do not. Metadata sources create `document_sources`, not implicit duplicate link records.

Link occurrence order is the order of opening link syntax in the canonical body, starting at zero. Reference definitions are not occurrences; each use is an occurrence. Both resolved and unresolved internal links are retained in this order. Alias display text and original link syntax MUST be preserved.

A missing document, missing heading, ambiguous target, or unsupported anchor MUST produce a warning without rejecting an otherwise valid file. If the document resolves but its heading does not, the document ID MAY still be recorded, but the unresolved heading diagnostic MUST remain available. A failed lookup MUST NOT bind the link to an arbitrary document.

### 7.4 Attachments and embeds

Markdown images and Obsidian embeds MUST be preserved as source. Core v1 does not promise to copy binary attachments or recursively expand another document's body. Exporters MUST disclose this limitation and SHOULD report referenced local attachments that are unavailable. An implementation claiming attachment portability MUST include a separate documented attachment profile.

## 8. Structural parsing and chunking

Processors MUST parse document structure; line-based searches for `#` or `[[...]]` alone are insufficient. Frontmatter MUST be separated before Markdown parsing so its delimiters and example values do not become body content.

Chunking is a retrieval operation, not an authoring requirement. Agents MUST NOT write database chunk IDs, embedding vectors, or artificial chunk delimiters into knowledge files.

A conforming chunker MUST:

1. Work against one canonical document revision at a time.
2. Use root-level body headings as section boundaries; headings nested inside quotes or lists are not document-section boundaries.
3. Retain document title and heading ancestry as retrieval context, with `heading_path` ordered from outermost to innermost heading.
4. Preserve paragraphs, tables, fenced code blocks, Mermaid diagrams, and list items as complete structural units where possible.
5. Never split a code fence, Mermaid block, or table merely to meet a target size.
6. Store source byte ranges and the chunker version so passages can be traced back to the authored document.
7. Cover all non-frontmatter body content through original source spans, allowing overlap but not silent omissions.

Chunk `content` MUST equal the UTF-8 text in its stored source byte range. Heading context and embedding wrappers are separate derived inputs and MUST NOT be inserted into that source slice. Each boundary MUST fall between UTF-8 code points. An introductory passage before the first heading has an empty heading path.

V1 does not prescribe a model-specific token budget. Each chunker version MUST publish its target size and counting method. An indivisible block exceeding the target MUST remain intact and produce `W_OVERSIZED_BLOCK`. If a complete chunk cannot be embedded within the chosen model's limits, the embedding operation MUST emit `W_EMBEDDING_INPUT_TOO_LARGE` and MUST NOT silently truncate it. The document and lexical retrieval remain available.

Changing chunking policy MUST change `chunker_version` and regenerate affected derived records deliberately. It MUST NOT create an authored content revision merely because a retrieval algorithm changed.

### 8.1 Rechunking and worker identity

V1 stores one published chunk set per document revision. A published chunk ID permanently identifies its original revision, source range, content, heading context, and chunker version; these fields MUST NOT be updated in place. Regenerating a set MUST allocate fresh chunk IDs, even when its ordinal positions repeat. IDs MUST NOT be reused or reset through `TRUNCATE`.

Compute a replacement layout outside the write transaction. Under the knowledge base lock, verify the expected existing chunk IDs/version, remove their embedding rows before deleting their chunk rows, insert the complete replacement set, and commit atomically. A concurrent replacement invalidating that expected set MUST cause recomputation or rejection, not a mixed layout. Readers MUST see the old complete set or the new complete set, never a partially replaced sequence.

Embedding jobs carry `chunk_id`, `profile_id`, and the exact expected `input_hash`. Model calls run outside database locks. Before publishing a result, the worker MUST acquire the knowledge base lock and confirm the chunk still exists, the immutable profile still matches, and the hash equals the input reconstructed from that chunk and revision. If any check fails, discard the result. A result for a removed chunk MUST NOT be redirected to a new chunk sharing its ordinal. Replacement embeddings are regenerated or reused by compatible profile and input hash after publication.

## 9. Embedding inputs

Embeddings are derived data and are not part of this file format. Their absence MUST NOT make a knowledge document invalid.

An embedding profile MUST define the model identity, dimensions, relevant model parameters, normalization, distance metric, and deterministic formatting of document and query inputs. If the provider exposes a model revision, the profile SHOULD record it.

The document input SHOULD include title, heading ancestry, and the complete chunk content. The exact input's UTF-8 bytes determine `input_hash`. Query embeddings and stored embeddings MUST use compatible profiles; equal vector dimensions alone are not sufficient.

Exporting a Markdown vault MUST NOT require serializing vectors or database chunk IDs into authored files. Database backups and retrieval-index transfers are separate operations.

### 9.1 Lexical retrieval fallback

Lexical retrieval MUST offer a literal mode that matches the complete query as a case-sensitive substring of current eligible titles, summaries, or chunk content, with no wildcard interpretation. Default search MUST use this fallback if full-text search has no searchable tokens or produces no hits. Responses MUST disclose the applied mode and pagination; they MUST NOT silently omit part of the candidate corpus. This covers short identifiers such as `Go` and `CI`, stopwords, and CJK substrings without claiming that the default full-text parser indexes them. The deployment's parser, token-size, and stopword configuration must be disclosed as specified in the [schema's search contract](tribal_schema.md#lexical-search-behavior).

## 10. Validation and diagnostics

Validation has four stages:

1. **File and YAML validation:** Encoding, delimiters, strict types, required fields, and supported schema version.
2. **Content validation:** Nonempty body, explicit fence closure, metadata semantics, and source-section references.
3. **Vault validation:** Unique identities, portable path uniqueness, knowledge base/domain assignment, and link resolution.
4. **Optional checks:** Mermaid parsing, external evidence availability, style, and embedding readiness.

Errors prevent the affected write. Warnings preserve the document and report a limitation or recommendation. A batch import MUST validate all selected files and its planned path/ID assignments before publishing any document-head changes; it MUST either publish the complete selected batch atomically or publish none. Asynchronous embedding work occurs after that commit.

Diagnostics MUST include a stable code, severity, message, file path, and line/column location when one is available. Locations refer to the normalized imported file before removal of any transport line. They SHOULD include a metadata key or suggested correction when useful. A validator MUST disclose which optional checks it performed; an unchecked diagram MUST NOT be reported as syntax-validated.

| Code | Severity | Condition |
|---|---|---|
| `E_ENCODING` | Error | Invalid UTF-8, BOM, or NUL content. |
| `E_FRONTMATTER` | Error | Missing/unterminated frontmatter, invalid YAML, duplicate keys, or prohibited YAML constructs. |
| `E_REQUIRED_FIELD` | Error | Required metadata is absent or blank. |
| `E_FIELD_TYPE` | Error | A known field has the wrong type, format, length, or enum value. |
| `E_LIMIT` | Error | Canonical file or a decoded/projected value exceeds a Section 2.1 acceptance limit. |
| `E_SCHEMA_VERSION` | Error | Unsupported `schema_version`. |
| `E_IDENTITY_COLLISION` | Error | Duplicate document ID in the selected vault state. |
| `E_PATH` | Error | Invalid path or portable path collision. |
| `E_ASSIGNMENT` | Error | Unknown or mismatched knowledge base/domain assignment. |
| `E_CONTEXT` | Error | Invalid/duplicate working context, dangling source context, missing explicit file root, invalid known-profile fields, or obsolete repository/Git root properties. |
| `E_EMPTY_BODY` | Error | Body has no non-whitespace text content. |
| `E_UNCLOSED_FENCE` | Error | A fenced block has no explicit closing fence. |
| `E_SOURCE` | Error | Invalid source object or unresolved/ambiguous evidence section. |
| `E_VERIFICATION` | Error | `verified` lacks a verifier, timestamp, or source. |
| `E_TRANSPORT` | Error | Invalid or unrecognized reserved transport metadata. |
| `E_BASE_REVISION_REQUIRED` | Error | A changed existing document has no base revision. |
| `E_REVISION_CONFLICT` | Error | A changed existing document was edited against a different revision. |
| `W_NORMALIZED` | Warning | Import normalized line endings or appended the final newline. |
| `W_UNKNOWN_PROPERTY` | Warning | Preserved property is not interpreted by Tribal. |
| `W_STYLE` | Warning | Recommended writing or heading structure is not followed. |
| `W_LINK_UNRESOLVED` | Warning | Document or heading target does not exist. |
| `W_LINK_AMBIGUOUS` | Warning | Multiple document or heading targets match. |
| `W_WIKILINK_SYNTAX` | Warning | Malformed wikilink candidate is preserved literally and creates no edge. |
| `W_EXTENSION_UNSUPPORTED` | Warning | Source is preserved but an extension is not semantically supported. |
| `W_CONTEXT_UNCHECKED` | Warning | An unfamiliar context/source type is preserved under its common shape, but type-specific semantics were not validated. |
| `W_MERMAID_UNCHECKED` | Warning | No diagram parser was used. |
| `W_MERMAID_SYNTAX` | Warning | Advertised renderer cannot parse the diagram. |
| `W_DIAGRAM_DESCRIPTION` | Warning | Diagram lacks a nearby prose explanation. |
| `W_SOURCE_UNAVAILABLE` | Warning | An optional availability check could not locate evidence or an attachment. |
| `W_OVERSIZED_BLOCK` | Warning | An indivisible block exceeds the chunker's target. |
| `W_EMBEDDING_INPUT_TOO_LARGE` | Warning | Complete embedding input exceeds the selected model's limit. |

## 11. Import, export, and revision transport

### 11.1 Authored properties versus service properties

Database revision IDs, author attribution, timestamps, hashes, and current-head pointers are managed by Tribal. Agents MUST NOT invent them in ordinary authored metadata. The document's `id` is different: it is required authored identity and MUST persist through export.

An exporter SHOULD insert its one transport property immediately after the opening frontmatter delimiter:

```yaml
---
tribal_base_revision: "efdd5a86-6efb-4b86-83a2-ac82fd66452d"
schema_version: 1
```

This excerpt illustrates the preferred insertion point, not a complete document. An importer MUST accept `tribal_base_revision` anywhere in the top-level block mapping, with a plain, single-quoted, or double-quoted string scalar whose parsed value is a canonical non-nil UUID. The entry MUST occupy exactly one physical line, no longer than 256 UTF-8 bytes; a trailing YAML comment is allowed and belongs to transport metadata. Quoted keys are allowed if their parsed key is exactly `tribal_base_revision`. Its entire physical line is removed before canonical content hashing or storage; all other authored bytes are preserved. Duplicate, multiline, non-string, overlong, or malformed entries are errors. Do not reserialize the surrounding YAML to remove the entry.

Editors MUST preserve this token while changing an exported file. A newly authored document does not need it.

### 11.2 Import behavior

- **Unknown document ID:** Create a document and initial revision after validation and assignment checks. A foreign base token from another installation does not import revision history and MAY be ignored for this initial creation.
- **Existing document, unchanged canonical content and path:** Return a no-op without creating a revision, even if the base token is stale or absent. Import MUST NOT restore a soft-deleted document implicitly.
- **Existing document, changed content or path:** Require a base token matching its current revision, or the equivalent explicit expected-revision argument supplied by the API. Conflicting token and API arguments are an error.
- **Stale base:** Reject the changed write with `E_REVISION_CONFLICT`; return current identity and revision information for deliberate reconciliation. Do not overwrite or automatically merge authored content.
- **Missing base:** Reject a changed existing document with `E_BASE_REVISION_REQUIRED`.
- **Soft-deleted document:** Require an explicit restore operation with the expected current revision; ordinary file import MUST NOT restore it.

The importer MUST compare revisions and update the document within a transaction. New content, extracted metadata, sources, links, chunks, current path, and the current revision pointer MUST become visible together. A `verified` declaration is interpreted as authored evidence metadata, not as permission to execute source commands.

Missing files in an imported directory MUST NOT imply deletion. V1 import/export is explicit snapshot interchange, not continuous bidirectional synchronization. Deletion and restoration require explicit operations.

### 11.3 Export behavior and round trips

An export MUST use a consistent snapshot of the selected documents. It MUST preserve document IDs, knowledge base/domain assignments, interpreted metadata, body content, evidence, original link syntax, code, tables, diagrams, and unknown properties. It MUST insert or refresh the base-revision transport line without otherwise reserializing frontmatter.

For an unchanged supported vault, export followed by import MUST produce no new authored revisions. Import into a fresh destination and subsequent export MUST preserve authored canonical bytes, document IDs, file paths, and supported resolved relationships; transport revision IDs and installation-specific database record IDs may differ. This promise does not include historical revision chains or derived chunks and vectors.

Relationship preservation applies to a complete knowledge base vault with targets and headings resolvable from the exported authored source. A partial export MUST report resolved dependencies omitted from that export; it cannot promise their resolution in a fresh destination. Stale cached link bindings that disagree with current source-path resolution are not conforming resolved relationships for this guarantee.

A deliberate rename or move is an authored location change. Any related link rewrites MUST be explicit edits committed with their affected documents; exporting a vault MUST NOT silently rewrite other documents to hide broken links. Current link-resolution projections MUST be refreshed after path changes. New unresolved links after a move are reported; preserving their intended resolution requires explicit source-link rewrites. Title and alias changes do not change identity. Historical link bindings MAY be retained separately from current-vault lookup behavior.

### 11.4 Serialized publication and path swaps

For v1, every mutation of a knowledge base's state MUST start its database transaction by locking its `knowledge_bases` row with `SELECT ... FOR UPDATE`. This includes document creates, content updates, moves, deletions, restores, permanent purges, chunk-set replacement, and embedding publication. Acquire knowledge-base locks first, then any document locks in ascending document UUID order. Operations spanning knowledge bases MUST acquire their locks in ascending UUID order. This deliberately simple publication policy may be optimized in a future protocol, but per-document locks alone are not sufficient for portable path uniqueness. These locks organize Tribal publication and do not lock any external context such as a Git repository or dataset.

File parsing and external work MAY occur before locking, but database-dependent checks MUST be repeated under the lock against current committed state, using locking/current reads rather than a previously established consistent-read snapshot. Check expected revisions, knowledge base/domain assignments, all final paths, and portable collision reservations, including unaffected and soft-deleted documents. A losing concurrent creator MUST receive `E_PATH` after the winner commits; it MUST NOT publish a conflicting path. A failed batch rolls back every selected document change.

MySQL unique-key checks are immediate, so a batch swapping occupied paths MUST stage every affected existing document at `.tribal-staging/<document-uuid>.md` inside the transaction before assigning final paths. The reserved namespace is unavailable to authors and exporters. Stage only `documents.vault_path`; create historical revision rows with their final authored paths. Insert new documents after vacated paths are staged. Temporary paths MUST never commit, appear in exports, or create extra revisions. Any error rolls back staging with the rest of the transaction. Readers use committed snapshots and MUST NOT use dirty reads.

### 11.5 Current link projection refresh

Before committing a create, content/heading update, move, delete, restore, or purge, the service MUST recompute resolution for **all internal link occurrences in current revisions of nondeleted documents in that knowledge base**, including source documents outside the selected write batch. Resolve against the planned final committed namespace. Archived or superseded targets still resolve if they exist; soft-deleted targets do not. Duplicate basenames include all nondeleted targets regardless of lifecycle status.

This full refresh is the v1 correctness baseline. It covers a newly created duplicate filename making an unchanged `[[Setup]]` ambiguous, heading edits invalidating incoming anchors, and a deletion or move invalidating existing bindings. Clear a formerly resolved `target_document_id` when its document becomes missing or ambiguous. Keep a uniquely resolved document ID when only its heading is missing/ambiguous, with an explicit diagnostic. Syntax, occurrence identity, source revisions, and authored text remain unchanged.

Bindings and diagnostics MUST describe the same namespace state as the document-head updates and become visible atomically. A service MAY compute diagnostics on demand from that same committed snapshot rather than persist them; it MUST NOT return stale success diagnostics. Historical source revisions retain their historical bindings and are not rewritten by this current-head refresh.

Graph and export readers MUST use one committed read snapshot per operation, joining each source occurrence to its document's `current_revision_id`. Reading heads and bindings in separate autocommit snapshots is not a consistent graph read. Index/cache optimizations MAY replace a full refresh only if they produce identical results and publication atomicity.

## 12. Mapping to the database schema

The companion [database schema](tribal_schema.md) stores the contract as follows:

| File information | Database representation |
|---|---|
| `id` | `documents.id`, also referenced by `document_revisions.document_id`. |
| `knowledge_base` | Lookup of `knowledge_bases.knowledge_base_key`; resolved UUID becomes `knowledge_base_id`. |
| `domain` | Lookup of `domains.domain_key` within that knowledge base; resolved UUID becomes `domain_id`. |
| File path | `documents.vault_path` and the new revision's historical `vault_path`. |
| `schema_version`, title, summary, kind, lifecycle, verification timestamp/state | Corresponding `document_revisions` columns. |
| `scope` | `document_revisions.scope`, defaulting to `{}`; no external-resource or Git assumptions. |
| `contexts` | `document_revisions.contexts`, defaulting to `[]`; Git fields exist only inside an explicitly typed context. |
| Tags and aliases | JSON arrays on `document_revisions`, defaulting to `[]`. |
| Complete canonical file | `document_revisions.markdown`; exact bytes determine `content_hash`. |
| `verified_by`, presentation properties, and extensions | Preserved in canonical Markdown; no separate SQL column is required by the current schema. |
| `sources` | `document_sources`; `type` maps to extensible `source_type`, `section` to `section_anchor`, `context` to `context_key`, and generic `revision` to `source_revision`. The API validates membership of context keys in this revision's JSON contexts. |
| Parsed internal body links | `document_links`, preserving occurrences and unresolved references. |
| Source passages and heading context | `document_chunks`. |
| Embedding configuration and generated vectors | `embedding_profiles` and `chunk_embeddings`; not authored in files. |
| Import caller and time | Revision `author_type`, `author_id`, and `created_at`, supplied by the service. |
| Transport base token | Expected revision check only; not canonical authored content. |

The SQL schema enforces structural relationships and broad value constraints. A format validator enforces this specification's additional rules. For example, the SQL schema allows a null current revision during creation, but the service MUST NOT publish a live document without its initial revision.

## 13. Complete authoring examples

These are fictional examples, not claims about the Tribal project. The referenced knowledge bases/domains must be configured to import them. External resources and related knowledge documents are not supplied here, so availability and unresolved-link warnings are expected when checking the examples in isolation. Git is declared only by the software-work example, not by the common format.

### 13.1 Non-software finding without Git

Suggested vault path: `botany/Germination observations.md`.

````markdown
---
schema_version: 1
id: "00000000-0000-4000-8000-000000000008"
title: "Germination observations"
knowledge_base: "fixture-kb"
domain: "botany"
kind: "finding"
summary: "A fictional trial observation with a non-Git notebook version."
scope:
  population: "illustrative bean-seed sample"
  conditions: "indoor trial"
contexts:
  - key: germination-trial
    type: experiment
    locator: "urn:example:seed-trial-2026"
    details:
      method: "daily visual inspection"
sources:
  - type: observation
    locator: "field-notebook:trial-2026/entry-12"
    context: germination-trial
    revision: "notebook-page-12"
    section: "Observation"
    details:
      observed_at: "2026-10-20T12:00:00Z"
---

# Germination observations

## Observation

In this fictional trial, eight of ten seeds had sprouted at the recorded
inspection. This is illustrative data, not a claim about a real experiment.

## Applicability

This note describes only the illustrative sample and inspection conditions.
No software project, command, Git repository, branch, or commit is required.
````

### 13.2 Software overview with an explicitly declared Git context

Suggested vault path: `authentication/How authentication works.md`.

````markdown
---
schema_version: 1
id: "393cfae9-c6ce-49bd-8abe-914b8dfdfd8a"
title: "How authentication works"
knowledge_base: "example-knowledge"
domain: "authentication"
kind: "overview"
summary: >
  Explains authentication startup, session lookup, configuration,
  and its database dependency.
tags:
  - authentication
  - architecture
aliases:
  - Authentication architecture
scope:
  environments:
    - development
    - production
contexts:
  - key: application-source
    type: git_repository
    locator: "https://example.org/example-service.git"
    details:
      branch: main
verification_state: "unverified"
sources:
  - type: "code"
    locator: "src/server/start.ts"
    context: application-source
    section: "Startup sequence"
    details:
      symbol: "startServer"
---

# How authentication works

## Architecture

The authentication service validates requests and uses the session
store to resolve stored sessions.

| Component | Responsibility |
|---|---|
| Authentication service | Validate request credentials |
| Session store | Resolve and invalidate sessions |
| Database connection | Provide access to keys and sessions |

## Startup sequence

The database connection is established before authentication loads
its signing keys. The server then starts accepting requests.

```mermaid
flowchart LR
    Database[Initialize database] --> Auth[Initialize authentication]
    Auth --> Ready[Accept requests]
```

The dependency is documented separately in
[[authentication/Database initialization dependency]].

## Configuration

The following illustrative code shows the required ordering:

```typescript
await connectDatabase();
await initializeAuth();
await startHttpServer();
```

## Known limitations

This overview has not been verified against alternative key providers.
See [[database/Connection lifecycle]] for database initialization details.
````

## 14. Minimum conformance cases

An implementation claiming v1 support MUST demonstrate the following behaviors. These are acceptance requirements for a future validator/importer, not a claim that one is implemented here.

The [review-edge fixture package](fixtures/markdown_v1/README.md) supplies complete baseline files, changed-file overlays, canonical SHA-256 hashes, link expectations, and transaction outcomes. Its examples are synthetic test data. Fixture integrity checks do not demonstrate a working importer or runtime Obsidian compatibility.

| Case | Expected result |
|---|---|
| Complete short finding with no headings and valid required metadata | Accept. |
| Overview containing a table, Mermaid diagram, and ordinary code fence | Accept and preserve all three structures. |
| Summary of 8,193 ASCII bytes, recorded target of 1,025 code points, or canonical file over 8 MiB | Reject with `E_LIMIT` before writing; never truncate. |
| Required field missing or `schema_version` is a string | Reject with a required-field or type diagnostic. |
| Duplicate YAML key, YAML alias, or custom YAML tag | Reject. |
| Note has no working context, Git fields, or code sources | Accept without probing Git or inheriting context from its domain. |
| Same domain contains Git-work notes, ordinary-folder notes, and general notes | Accept each according to its own explicit contexts; no domain-wide Git assumption. |
| Experiment source has `revision: notebook-page-12` | Accept as an opaque non-Git version; no SHA requirement. |
| Filesystem root URI omits a trailing slash | Append beneath the complete root directory; do not replace its last path segment. |
| Known filesystem/Git profile supplies a relative root | Reject with `E_CONTEXT`; never supply the importing process's working directory. |
| Publication selects Git but supplies an edition string as `revision` | Reject with `E_SOURCE`; store edition in `details` and use a Git object ID for the selected revision. |
| Git context's `details.commit` or selected source `revision` is an abbreviated SHA | Reject with `E_CONTEXT` for context fields or `E_SOURCE` for source fields. |
| Source selects an absent context key or uses a relative file path without an explicit root | Reject with `E_CONTEXT`; do not fall back to a vault, current directory, or default Git checkout. |
| Unknown context/source type has a valid common shape | Preserve and report `W_CONTEXT_UNCHECKED`; do not impose Git rules. |
| `verified` document without a source, verifier, or timestamp | Reject with `E_VERIFICATION`. |
| Source refers to a missing or duplicate heading | Reject with `E_SOURCE`. |
| Code example contains `[[Not a link]]` or `# Not a heading` | Preserve literally; extract neither link nor heading. |
| Mermaid contains node edges or apparent wiki syntax | Preserve diagram source; create no graph edges from it. |
| Table cell contains an escaped-pipe wikilink alias | Resolve the link and preserve its original syntax. |
| Overlapping Markdown/wikilink, escaped opening, malformed alias, or opaque embed | Follow the Section 7.2.1 precedence fixtures exactly. |
| Two domains contain the same filename stem | Bare link is ambiguous; an exact qualified path resolves. |
| Root `Guide.md` and nested `database/Guide.md` coexist | Bare wikilink remains ambiguous; relative Markdown link selects the root document. |
| Link names a missing heading in an existing document | Preserve the link and issue an unresolved-heading warning. |
| Only the casing of a link target is wrong | Preserve it and report an unresolved target; do not guess. |
| Two files have identical IDs or portable-colliding paths | Reject the selected batch without publishing partial changes. |
| Unsupported extension or unavailable Mermaid parser | Preserve source and disclose the unchecked/unsupported feature. |
| A table exceeds the chunk target | Keep it intact and warn; do not truncate it. |
| Exported file is re-imported unchanged | No new content revision. |
| Only transport-entry position or string quoting changes | Canonical hash unchanged; no new content revision. |
| Valid Properties-panel edit changes summary with a retained current base token | Create one revision; preserve UTC verifier text and structured evidence. Record actual tested Obsidian version separately. |
| Path-only move with matching base | Create one location revision; preserve canonical content hash and document ID. |
| Rename plus companion source-link edits | Publish all selected heads and refreshed graph bindings together. |
| Batch swaps two occupied paths | Use reserved temporary paths internally; commit only final paths and one revision per moved document. |
| Concurrent creates propose `Setup.md` and `setup.md` | Serialize publication; exactly one succeeds and the other receives `E_PATH`. |
| New file makes an unchanged source's bare target ambiguous | Refresh that source's binding/diagnostic in the same commit without creating a source revision. |
| Rechunking replaces passages while an old embedding job finishes | Fresh chunk IDs; discard the stale result; no vector attaches by ordinal. |
| Changed existing file has an old base token | Reject with `E_REVISION_CONFLICT`. |
| A file is absent from an imported directory | Do not delete its database document. |
| Knowledge is imported into a fresh installation and exported | Preserve canonical authored bytes, IDs, paths, and supported relationships; regenerated transport IDs may differ. |

## 15. References

- [GitHub Flavored Markdown specification](https://github.github.com/gfm/).
- [Obsidian Properties](https://obsidian.md/help/properties).
- [Obsidian internal links](https://obsidian.md/help/links).
- [Obsidian advanced formatting, tables, and diagrams](https://obsidian.md/help/advanced-syntax).
- [Mermaid documentation](https://mermaid.js.org/intro/).
- [Tribal database schema](tribal_schema.md).
- [Review-edge fixtures and expected outcomes](fixtures/markdown_v1/README.md).
