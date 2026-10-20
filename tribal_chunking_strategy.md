# Tribal Markdown Chunking Strategy v1

Status: **Proposed; chunker not yet implemented**

Date: **2026-10-20**

This document defines a proposed retrieval chunking policy for validated Tribal Markdown. It builds on [the Markdown format specification](tribal_markdown_spec.md#8-structural-parsing-and-chunking), [the parser API](docs/parser_api.md), and [the storage schema](tribal_schema.md). The existing parser and validator are implemented; the chunker, embedding pipeline, and database publication described here are future work.

The words MUST, MUST NOT, SHOULD, and MAY describe the proposed implementation contract. This policy adds detail to the Markdown specification without changing its authoring rules.

## 1. Purpose and approach

Chunks should retrieve a useful passage with enough context to understand it, while preserving a precise route back to the original document. A short finding and a long reference document use the same policy.

The chosen approach is **structure first, size second**: identify document sections and complete Markdown units, then pack adjacent units toward a soft byte target. Knowledge bases and domains select the retrieval corpus; they do not change how syntax is chunked. No Git repository, software project, particular natural language, or fixed set of English headings is assumed. Working contexts come only from the note's declared metadata.

| Approach | Tradeoff | Decision |
|---|---|---|
| Fixed character or token windows | Simple sizing, but boundaries can cut through tables, code, equations, or reasoning. | Do not use for the initial policy. |
| Structural sections with size-aware packing | Deterministic source ranges and intact rich content; some chunks exceed the target. | Use for v1. |
| Model-generated semantic boundaries | Adds model calls and another source of variability; requires separate quality evaluation. | Consider later as a separately versioned policy. |

The initial byte target is a design starting point, not a claim about optimal retrieval quality. Evaluate it against actual questions before changing it.

## 2. Policy identity and defaults

| Setting | Initial value |
|---|---|
| `chunker_version` | `tribal-structure-bytes-v1` |
| Target source size | 4,096 UTF-8 bytes per chunk. |
| Counting method | Exact length of the canonical source slice encoded as UTF-8. |
| Overlap | None. Neighbor expansion happens during retrieval. |
| Section boundary | Every body heading outside a list, blockquote, or other container. |
| Minimum size | None; short sections remain short. |
| Hard per-chunk source target | None beyond the document's existing 8 MiB acceptance cap. |
| Oversized atomic unit | Preserve intact, emit `W_OVERSIZED_BLOCK`, and continue. |

Bytes are available without an embedding provider or tokenizer. **4,096 bytes does not mean 4,096 tokens**, and there is no fixed conversion across languages, equations, and code. The embedding profile separately checks the complete model input against its actual limits.

The version names a complete frozen policy, including the target, packing rules, atomic-unit rules, and parser behavior affecting boundaries. Changing these rules requires a new `chunker_version`, even if the algorithm's general name remains the same. Published implementations must record the parser and dependency versions used for that policy. Embedding-model changes alone do not require new source chunks.

## 3. Input and source invariants

The chunker accepts a successfully validated document attached to one specific Tribal document revision. It MUST NOT publish chunks from a partial parse containing validation errors. Warnings, including unchecked Mermaid or math semantics, do not by themselves prevent chunking.

Use the parser's `canonical_markdown`: LF-normalized authored text with the optional `tribal_base_revision` transport line removed. Do not reserialize YAML, reformat the body, normalize Unicode, or render Markdown before choosing offsets.

Every published chunk MUST satisfy:

```python
canonical_bytes = canonical_markdown.encode("utf-8")
content = canonical_bytes[start_byte:end_byte].decode("utf-8")
```

The source range is zero-based and half open. Its boundaries MUST fall between UTF-8 code points, and `end_byte` MUST exceed `start_byte`. Offsets refer to the complete canonical file, including its frontmatter, even though frontmatter itself is excluded from chunk content.

The initial policy partitions the complete body into ordered, adjacent source ranges:

- The first chunk starts at the first byte after the closing frontmatter delimiter and its LF.
- Each subsequent chunk starts exactly where its predecessor ends.
- The final chunk ends at the end of the canonical file.
- Concatenating all chunk contents reconstructs the canonical body exactly.

This includes blank lines, reference definitions, footnotes, comments, unsupported extensions, and the final newline. A range containing only whitespace is not silently dropped; normally whitespace is absorbed into an adjacent unit as described below.

Frontmatter is revision metadata. Do not emit it as a body chunk or repeatedly insert its YAML into chunks. Title, ownership, contexts, scope, tags, evidence, and lifecycle remain available through the owning revision. Do not add chunk markers or generated identifiers to the authored file.

## 4. Sections and heading context

A root-level heading means a heading outside a container, **not only an H1 heading**. Both ATX headings (`## Observation`) and Setext headings establish sections. Apparent headings inside code, diagrams, math, comments, or opaque HTML do not.

Create an initial section for any body source before the first root-level heading. Each root-level heading then starts a new section, ending immediately before the next root-level heading or at the end of the body. A heading's original source belongs to the section it starts. Never pack units from separate sections into the same chunk just to reach the target.

Maintain a heading stack. At a new heading of level `L`, remove stack entries with levels greater than or equal to `L`, then append the new heading. Do not invent missing ancestors when levels skip.

- `heading_path` is the stack's extracted heading text, outermost to innermost.
- Include an H1 title heading when present, even when it matches the document's metadata title.
- A pre-heading introduction has `heading_path: []`.
- Nested headings inside quotes or lists stay in the source but do not change this stack.
- Duplicate headings do not merge sections or make chunk identities collide.

Every chunk in a section shares that section's heading path. Compute this from the section model; do not copy an empty heading path from a generic parser gap block. A section containing only a heading remains a small chunk. There is no minimum-size merge across sections.

Set `section_anchor` to the section's heading text only when it is nonempty, plain inline text, and unique among the document's headings under the existing exact-heading rules. Otherwise use `NULL`, including for the introduction. Keep `heading_path` even when an anchor is unavailable. Source byte ranges remain the definitive locator; do not invent slugs or occurrence suffixes.

## 5. Structural units and protected content

Within a section, identify source-backed units using Markdown block structure and the parser's recognized opaque regions. The table defines which boundaries are available to the initial chunker.

| Content | Treatment |
|---|---|
| Paragraph | Keep the complete paragraph, including inline code, inline math, links, and emphasis. Do not split sentences or words to satisfy the target. |
| Root-level heading | Keep all of its source together, including a Setext underline. It begins its section. |
| GFM table | Keep the complete table, including header, delimiter, rows, alignments, and escaped pipes. Never repeat its header in another source chunk. |
| Fenced or indented code | Keep the complete block, including fence markers and info string when present. Do not split by code lines or inferred functions. |
| Mermaid fence | Keep the complete diagram source and fences. Its graph edges are not knowledge links. |
| Display math | Keep the entire recognized math region, including delimiters and interior blank lines. Do not split equations, aligned environments, or matrices. |
| List | Keep the whole list if it fits. An oversized list may be partitioned only between complete immediate list items, as described below. |
| Blockquote or callout | Keep the whole container, including nested content and quote prefixes. An oversized container stays intact in v1. |
| Reference or footnote definition | Keep each complete definition, including continuation lines. Preserve it even when its uses occur in another chunk. |
| HTML block, comment, embed, or other recognized opaque region | Preserve the whole recognized region without evaluating it or extracting speculative relationships. |
| Thematic break or other ordinary block | Keep its complete original source. |

For an oversized list, obtain the immediate item source ranges from the structural parse. Each item includes its original marker, continuation lines, nested lists, code, tables, diagrams, and other descendants. Pack complete items in their original order. Do not synthesize numbering, indentation, quote prefixes, or closing syntax. An item exceeding the target remains intact and receives the oversized warning. If reliable item boundaries are unavailable, preserve the complete list and warn instead of guessing.

List partitioning does not split a table or code block nested within an item. Parent containers and their descendants are alternative levels of segmentation, not additional copies of content. A list and a nested Mermaid block MUST NOT both be emitted as overlapping source units. If a protected region crosses apparent ordinary-block boundaries, combine those blocks into one unit covering the complete region before packing; do not cut the protected region to make the block map simpler.

For units inside a section, attach each inter-unit source gap to the preceding unit; attach leading source to the first unit. If the section has no recognized block, preserve its entire range as one source unit. Apply the same rule inside a list when partitioning its immediate items. This makes whitespace and less familiar syntax part of the exact partition without manufacturing filler text.

A chunk is a passage from an original document, not necessarily a standalone renderable document. For example, a reference-style link's definition may live in another chunk. A renderer can consult the full revision; the chunker must not copy definitions into `content`. A table or diagram's adjacent explanation will share a chunk when it fits under ordinary packing; otherwise heading context and retrieval of neighbors supply context.

### 5.1 Math and current parser limits

The current parser preserves dollar-delimited inline math, `$$` display math, and multiline `\[` / `\]` display math as unchecked content. It does not render equations or validate LaTeX. Inline `\(` / `\)` is not currently recognized as a math region; the chunker must not advertise support for additional delimiters without parser changes and tests.

Math inside a paragraph is protected by keeping that paragraph whole. Display math needs an explicit protected source range, including blank lines, rather than a collection of apparent Markdown paragraphs. Existing `W_EXTENSION_UNSUPPORTED` diagnostics must remain visible; successful chunking does not establish mathematical validity.

## 6. Deterministic packing

First form the sections and partition each section into the units above. Refine oversized lists at safe immediate-item boundaries before packing. Then process units in source order, independently for each section:

```text
for each section:
    pending = empty

    for each unit in section:
        if source_bytes(unit) > 4096:
            flush pending if nonempty
            emit unit as one chunk
            report W_OVERSIZED_BLOCK for this unit
        elif pending is nonempty and bytes(pending + unit) > 4096:
            flush pending
            pending = unit
        else:
            append unit to pending

    flush pending if nonempty
```

`pending + unit` denotes adjacent original source, not string concatenation with generated separators. Count all source bytes, including indentation, delimiters, and attached gaps. A unit of exactly 4,096 bytes fits without an oversized warning.

Do not rebalance earlier chunks, borrow units across a section boundary, duplicate a heading at each split, or pad a short final chunk. These choices keep the policy deterministic and its source mapping simple. Given the same canonical revision and policy version, the ordered ranges, contents, and heading metadata MUST be identical. Database-assigned chunk IDs may differ between regenerations.

### 6.1 Example layout

For this schematic body:

````markdown
An introduction before the first heading.

# Seed observations

## Method

A short paragraph about the trial.

| Group | Seeds |
|---|---|
| A | 10 |

## Results

The measured proportion is $p = 8/10$.

$$
p = 0.8
$$
````

If each section is below the target, the result is:

| Ordinal | Source covered | `heading_path` |
|---|---|---|
| 0 | Introductory paragraph and its trailing blank line. | `[]` |
| 1 | `# Seed observations` and its trailing blank line. | `["Seed observations"]` |
| 2 | Complete Method section, including its table. | `["Seed observations", "Method"]` |
| 3 | Complete Results section, including its display equation. | `["Seed observations", "Results"]` |

A table larger than the target would occupy an intact chunk within its section and produce `W_OVERSIZED_BLOCK`. A very long paragraph follows the same conservative rule. Neither case is a reason to reject an otherwise valid note.

## 7. Output and storage mapping

Emit the following fields for each source chunk, matching the existing `document_chunks` design:

| Field | Meaning |
|---|---|
| `revision_id` | Owning Tribal document revision supplied by the service; not an external Git revision. |
| `ordinal` | Zero-based position in this revision's complete source-ordered chunk sequence. |
| `heading_path` | Ordered array of section heading text. |
| `section_anchor` | Unique plain heading text, or `NULL`. |
| `start_byte`, `end_byte` | Half-open canonical UTF-8 source range. |
| `content` | Exact decoded UTF-8 slice for that range. |
| `chunker_version` | Frozen policy identifier from Section 2. |

Database `id` values are allocated at publication. Ordinals are ordering information and MUST NOT be used as durable identities across revisions or replacements. Additional diagnostics and measurements can be returned alongside the layout; they do not require putting generated metadata in Markdown.

Ownership, contexts, applicability, evidence, and verification remain revision metadata. A chunk inherits that association through `revision_id`; its text alone does not establish that a claim is verified or applicable. Document links remain the parser's document-level occurrences. Chunking must not discover extra links by scanning raw code, diagrams, or math, or duplicate graph relationships just because content was segmented.

## 8. Embedding input and oversized content

Keep source chunking separate from embedding formatting. The source target counts `content` only. The embedding operation counts the **complete** input, including title, heading context, and any model-required formatting, using that profile's actual counting method.

A proposed text wrapper, to be frozen under an embedding profile, is:

```text
Title: <metadata.title>
Headings: <compact JSON array of heading_path>

<exact chunk content>
```

An implementation of this wrapper uses `Title: ` plus the title, LF, `Headings: ` plus a UTF-8 JSON array serialized with `ensure_ascii=False` and separators `(',', ':')`, two LFs, then the exact chunk content. It appends nothing else. This wrapper is embedding input only; it is never stored as `document_chunks.content`. Its exact UTF-8 bytes determine `input_hash`. A different wrapper requires a distinct immutable embedding profile.

If the complete input exceeds the selected embedding model's limit, emit `W_EMBEDDING_INPUT_TOO_LARGE` and leave that chunk unavailable for that profile. Preserve its source and lexical retrieval. Never truncate the chunk, remove table rows, shorten code, strip equations, or silently switch chunking policy to fit a model. If smaller passages are needed, create a separately versioned policy or deliberately change the authored document.

Unchecked math or Mermaid can still be included as preserved source in an embedding input; an embedding does not validate or execute that source. Profiles must disclose any provider-specific inability to process an input.

## 9. Retrieval context and overlap

The initial chunk set has no overlap. Overlap repeats text in storage and results and complicates exact source coverage. A future overlapping policy must receive its own version.

A retrieval response should return document identity and revision, title, heading path, byte range, and relevant ownership/applicability metadata with each passage. When a result needs adjacent explanation, the retrieval layer may fetch neighboring chunks from the **same revision**, applying an explicit context budget. It must disclose included ranges and deduplicate adjacent results before assembling agent context.

Neighbor expansion does not change chunk content, create a new chunk identity, or mix current and historical revisions. It is also not permission to inherit the context of a linked note. Retrieval should distinguish document verification metadata from independent proof of the retrieved passage's claims.

## 10. Diagnostics and publication

Use the validator's structured diagnostic envelope for chunking feedback: stable code, severity, path, source location when available, expected/actual values, and an actionable hint. Oversize diagnostics should also identify the source range, actual byte count, 4,096-byte target, and protected unit type.

- `W_OVERSIZED_BLOCK` means a complete structural unit exceeded this policy's source target. Chunking succeeds and preserves it.
- `W_EMBEDDING_INPUT_TOO_LARGE` is emitted by the embedding stage when complete model input cannot fit that profile. It does not invalidate the Markdown.
- Existing parser warnings about opaque or unchecked syntax remain available. Do not relabel them as validated merely because a chunk was emitted.
- A broken source-range invariant, inconsistent structural map, or mismatch with the expected canonical revision must fail the chunking operation with a precise operational diagnostic. Do not publish a partial layout or misclassify an implementation defect as invalid authored Markdown.

Canonical byte offsets and diagnostic line/column coordinates are different coordinate systems. Initial-ingest diagnostics use normalized submitted input before transport removal, as required by the Markdown specification; retain the parser's source mapping to translate them. Stored-revision processing can locate diagnostics directly in the canonical source. Use LF as the physical line separator; Unicode paragraph separators are preserved content.

Publication follows the existing schema and Markdown contracts: compute the layout outside database locks, verify the expected revision and old chunk set under the knowledge-base lock, and publish one complete set atomically. Replacements allocate fresh chunk IDs, remove dependent embedding rows before old chunks, and never reuse IDs or attach results by ordinal. Rechunking changes derived data without creating an authored revision.

Embedding jobs carry `chunk_id`, profile ID, and exact `input_hash`. Before publication, verify that the original chunk, profile, and reconstructed input still match. Discard stale jobs instead of redirecting their vectors to replacement passages. No Git commands or external evidence checks are required for any chunking step.

## 11. Parser integration work still required

The current public parser output is useful input, but it is **not yet a complete chunking intermediate representation**:

- `blocks` can contain overlapping parent containers and nested rich blocks. Normalize this hierarchy into a nonoverlapping source partition before packing.
- Root heading blocks provide section starts, but the public `headings` array also includes nested headings and does not expose plain-heading eligibility. Use a shared structural view to establish containment and anchor eligibility.
- The public output does not expose immediate list-item ranges, definition continuation ranges, or all opaque-region boundaries, including typed display-math spans. Add those to a shared parser projection before claiming full support for the policy.
- Generic gap blocks have empty heading paths. Derive their context from the enclosing section rather than treating them as introductions.
- Preserve or expose the canonical body-start offset and transport-removal source mapping. Do not estimate UTF-8 offsets using character counts or normalized-input line numbers.

Prefer a shared internal structural representation, or a versioned extension to the parser output, over a second set of regular expressions that can disagree about code, links, math, or containers. These are implementation prerequisites; this document does not change the parser's existing public API or claim that it already emits chunks.

## 12. Acceptance and evaluation

Implementation tests should establish the following before the policy is published:

| Case | Expected behavior |
|---|---|
| Short finding with no headings | One chunk when below target; empty heading path. |
| Introductory text followed by root headings | Introduction preserved; each section has its own heading path and source ranges. |
| Nested or skipped heading levels; duplicate or formatted headings | Correct stack without invented ancestors; unavailable exact anchors are `NULL`. |
| Headings inside lists, quotes, code, or opaque regions | No document-section boundary from nested/literal content. |
| Adjacent units totaling exactly 4,096 bytes | Pack together; no oversize warning. |
| Next unit would cross the target | Start another chunk at the unit boundary. |
| Oversized paragraph, table, fence, diagram, math region, or quote | Preserve intact; warn; do not truncate. |
| Oversized list containing nested code/table/math | Partition only between complete immediate items, preserving all descendant source. |
| Parent container plus nested rich-block parser spans | Every body byte represented exactly once under this policy. |
| Reference definitions, footnotes, blank lines, comments, and final LF | All retained in original order; no generated copies. |
| Non-ASCII text, combining characters, emoji, or Unicode line separators | Correct byte boundaries and source equality; only LF changes physical lines. |
| Transport token moves or is requoted without changing canonical source | Identical ranges and contents. |
| Same canonical source and frozen policy run twice | Identical layout and metadata. |
| Embedding wrapper pushes otherwise-small content over a model limit | Source unchanged; explicit unavailable embedding diagnostic. |
| Replacement finishes while an old embedding job is in flight | Fresh chunk IDs; old result discarded. |
| Botany, history, mathematics, ordinary folders, and explicit Git contexts | Same structural policy; no inferred working context. |

Check source-partition invariants for every output, not only selected examples: contiguous ranges, valid UTF-8 boundaries, exact source equality, and complete body reconstruction. Tests for future storage publication must be distinguished from pure chunker tests.

Evaluate retrieval separately using representative questions and expected evidence passages across domains. Record whether supporting passages were retrieved, how much irrelevant context was returned, context bytes and actual model tokens, oversized/unembeddable unit frequency, and the effect of neighbor expansion. Compare against a whole-document baseline and any candidate target sizes using the same corpus and retrieval setup. Do not present the initial 4,096-byte choice as a measured optimum until those evaluations exist.
