#!/usr/bin/env python3
"""Read-only structural validation for a complete Tribal v1 Markdown vault."""

from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass, field
from datetime import datetime
import json
import os
from pathlib import Path
import re
import sys

import yaml
from yaml.nodes import MappingNode, ScalarNode, SequenceNode
from yaml.tokens import AliasToken


@dataclass(frozen=True)
class ValidationIssue:
    path: str
    code: str
    message: str


COMMON_REQUIRED = {
    "spec_version", "id", "type", "title", "project_id", "created_at",
    "updated_at", "status",
}
COMMON_OPTIONAL = {
    "repository", "source_event_id", "observed_at", "session_id", "tags",
    "aliases", "superseded_by",
}
# Required metadata, optional metadata, and required H2 sections.
TYPE_RULES = {
    "project": (set(), set(), ("Summary", "Repositories", "Working context")),
    "repository": ({"repository_key"}, {"remote_url"}, (
        "Purpose", "Structure", "Working instructions", "Dependencies and connections")),
    "branch": ({"repository", "branch_name", "work_status"},
               {"base_commit", "head_commit"}, ("Intent", "Progress", "Remaining work")),
    "commit": ({"repository", "commit_hash"}, {"branch_name"}, (
        "Summary", "Commit message", "Affected files", "Verification")),
    "merge": ({"repository", "source_event_id", "observed_at", "source_ref",
               "source_commit", "target_branch", "target_before", "target_after", "merge_kind"},
              set(), ("Summary", "Integrated changes", "Conflicts and verification")),
    "push": ({"repository", "source_event_id", "observed_at", "remote_name"},
             {"remote_url"}, ("Summary", "Ref updates", "Verification")),
    "finding": (set(), set(), ("Observation", "Evidence", "Implications")),
    "insight": (set(), set(), ("Insight", "Basis", "Implications")),
    "decision": ({"decision_state"}, set(), (
        "Context", "Decision", "Rationale and alternatives", "Authority", "Consequences")),
    "handoff": (set(), {"branch_name", "head_commit"}, (
        "Goal", "Completed work", "Current state", "Blockers", "Next steps")),
    "guide": (set(), {"verified_at", "verified_commit"}, (
        "Purpose and scope", "Prerequisites", "Procedure", "Verification", "Troubleshooting")),
}
ENUMS = {
    "status": {"active", "archived", "superseded"},
    "work_status": {"planned", "in_progress", "blocked", "done", "abandoned"},
    "merge_kind": {"merge_commit", "fast_forward", "squash"},
    "decision_state": {"proposed", "accepted", "rejected"},
}
HASH_FIELDS = {"base_commit", "head_commit", "commit_hash", "source_commit",
               "target_before", "target_after", "verified_commit"}
DATE_FIELDS = {"created_at", "updated_at", "observed_at", "verified_at"}
REF_FIELDS = {"branch_name", "source_ref", "target_branch"}
LINK_FIELDS = {"repository", "superseded_by"}
RFC3339 = re.compile(
    r"\d{4}-\d{2}-\d{2}[Tt]\d{2}:\d{2}:\d{2}(?:\.\d+)?"
    r"(?:[Zz]|[+-](?:[01]\d|2[0-3]):[0-5]\d)\Z"
)
WIKILINK = re.compile(r"(?<!\\)\[\[([^\[\]\n]+)\]\]")
HEADING = re.compile(r"^ {0,3}(#{1,6})[ \t]+(.+?)[ \t]*$")


@dataclass
class _Note:
    path: str
    metadata: dict
    sections: dict[str, list[str]] = field(default_factory=dict)
    headings: set[str] = field(default_factory=set)
    links: list[tuple[str, str | None]] = field(default_factory=list)


# Explain why a path violates the vault-relative POSIX path rules.
def _path_problem(value: str) -> str | None:
    if not value or value.startswith("/") or re.match(r"^[A-Za-z]:", value):
        return "must be a nonempty vault-relative POSIX path"
    if "\\" in value or any(ord(char) < 32 or ord(char) == 127 for char in value):
        return "must not contain backslashes or control characters"
    if any(part in {"", ".", ".."} for part in value.split("/")):
        return "must not contain empty, '.' or '..' path components"
    return None


# Mask literal Markdown code and comments before inspecting document structure.
def _visible_markdown(body: str) -> str:
    """Mask code and HTML comments in source order, preserving line positions."""
    token = re.compile(r"^ {0,3}(`{3,}|~{3,})([^\n]*)$|(?<!`)(`+)(?!`)|<!--", re.M)
    pieces = []
    position = 0
    while match := token.search(body, position):
        pieces.append(body[position:match.start()])
        end = match.end()
        if match[1] and (match[1][0] != "`" or "`" not in match[2]):
            closing = re.compile(r"^ {0,3}" + re.escape(match[1][0]) + "{" + str(len(match[1])) + r",}[ \t]*$", re.M)
            close = closing.search(body, end)
            end = close.end() if close else len(body)
        elif match[3]:
            # Inline code closes with the same length run, even across lines.
            close = re.search(r"(?<!`)" + re.escape(match[3]) + r"(?!`)", body[end:])
            if close:
                end += close.end()
            else:
                pieces.append(match[0])
                position = end
                continue
        elif match[0] == "<!--":
            close = body.find("-->", end)
            end = close + 3 if close != -1 else len(body)
        else:
            pieces.append(match[0])
            position = end
            continue
        pieces.append("".join("\n" if char == "\n" else " " for char in body[match.start():end]))
        position = end
    pieces.append(body[position:])
    return "".join(pieces)


# Distinguish substantive section content from empty or TODO-only placeholders.
def _meaningful(text: str) -> bool:
    text = re.sub(r"<!--[\s\S]*?-->", "", text)
    for line in text.splitlines():
        if HEADING.match(line) or re.match(r"^\s*(?:`{3,}|~{3,})", line):
            continue
        stripped = re.sub(r"^[\s#>*\-+\d.)\[\]`~_]+", "", line).strip()
        if not re.search(r"\w", stripped):
            continue
        if re.match(r"(?i)^(?:todo|tbd|fixme|placeholder)(?:\b|:)", stripped):
            continue
        if stripped.lower().strip(" .![]<>") in {"coming soon", "fill in", "insert content here"}:
            continue
        return True
    return False


# Split a wikilink into its note path and optional heading target.
def _link_parts(raw: str) -> tuple[str, str | None]:
    target = raw.split("|", 1)[0]
    path, separator, heading = target.partition("#")
    return path, heading if separator else None


# Check locally decidable Git ref syntax without contacting Git.
def _ref_valid(value: str, *, short: bool = False) -> bool:
    return bool(value) and not (
        value in {"@", "HEAD"} or value.startswith(("/", "-"))
        or value.endswith(("/", ".")) or ".." in value or "//" in value
        or "@{" in value or re.search(r"[\x00-\x20\x7f~^:?*\[\\]", value)
        or any(part.startswith(".") or part.endswith(".lock") for part in value.split("/"))
        or (short and value.startswith("refs/"))
    )


# Parse one safe YAML mapping while retaining scalar styles for quote checks.
def _yaml_metadata(frontmatter: str) -> tuple[dict, dict[str, object]]:
    # Reject aliases before constructing anything, including recursive YAML.
    for token in yaml.scan(frontmatter):
        if isinstance(token, AliasToken):
            raise ValueError("YAML aliases are not allowed")
    loader = yaml.SafeLoader(frontmatter)
    try:
        node = loader.get_single_node()
        if not isinstance(node, MappingNode):
            raise ValueError("frontmatter must contain one YAML mapping")

        # Reject duplicate keys, nonstring keys, and nulls throughout the YAML tree.
        def check(current):
            if isinstance(current, MappingNode):
                seen = set()
                for key, value in current.value:
                    if not isinstance(key, ScalarNode) or key.tag != "tag:yaml.org,2002:str":
                        raise ValueError("YAML mapping keys must be strings")
                    if key.value in seen:
                        raise ValueError(f"duplicate YAML key: {key.value}")
                    seen.add(key.value)
                    check(value)
            elif isinstance(current, SequenceNode):
                for item in current.value:
                    check(item)
            elif current.tag == "tag:yaml.org,2002:null":
                raise ValueError("null values are not allowed; omit unavailable optional fields")

        check(node)
        styles = {key.value: value for key, value in node.value}
        return loader.construct_document(node), styles
    finally:
        loader.dispose()


# Read one note and collect its file, metadata, and Markdown format issues.
def _read_note(file: Path, path: str, issues: list[ValidationIssue]) -> _Note | None:
    # Attach a diagnostic to the current vault-relative note path.
    def issue(code, message):
        issues.append(ValidationIssue(path, code, message))

    try:
        raw = file.read_bytes()
        text = raw.decode("utf-8")
    except (OSError, UnicodeError) as error:
        issue("file.read", f"Cannot read UTF-8 Markdown: {error}")
        return None
    if raw.startswith(b"\xef\xbb\xbf"):
        issue("file.bom", "UTF-8 byte-order marks are not allowed")
    if b"\r" in raw:
        issue("file.newline", "Use LF line endings without carriage returns")
    if not raw.endswith(b"\n"):
        issue("file.newline", "Markdown must end with a newline")
    lines = text.split("\n")
    if not lines or lines[0] != "---":
        issue("frontmatter.missing", "File must begin with a --- YAML frontmatter delimiter")
        return None
    try:
        closing = lines.index("---", 1)
    except ValueError:
        issue("frontmatter.missing", "Missing closing --- frontmatter delimiter")
        return None
    try:
        metadata, nodes = _yaml_metadata("\n".join(lines[1:closing]))
    except (yaml.YAMLError, ValueError, TypeError, RecursionError, OverflowError) as error:
        issue("frontmatter.yaml", f"Invalid YAML frontmatter: {error}")
        return None
    kind = metadata.get("type")
    if not isinstance(kind, str) or kind not in TYPE_RULES:
        issue("metadata.type", "type must be one of: " + ", ".join(TYPE_RULES))
        return None
    required, optional, sections = TYPE_RULES[kind]
    allowed = COMMON_REQUIRED | COMMON_OPTIONAL | required | optional
    for key in sorted(COMMON_REQUIRED | required):
        if key not in metadata:
            issue("metadata.required", f"Missing required field: {key}")
    for key in sorted(metadata):
        if key not in allowed:
            issue("metadata.unknown", f"Unknown field for {kind}: {key}")
    dates = {}
    for key, value in metadata.items():
        if key == "spec_version":
            if type(value) is not int or value != 1:
                issue("metadata.version", "spec_version must be integer 1")
            continue
        if key in {"tags", "aliases"}:
            if not isinstance(value, list) or any(not isinstance(item, str) or not item.strip() for item in value):
                issue("metadata.list", f"{key} must be a list of nonblank strings")
            elif len(value) != len(set(value)):
                issue("metadata.list", f"{key} values must be distinct")
            elif key == "tags" and any(item.startswith("#") for item in value):
                issue("metadata.tags", "tags must not have a leading #")
            continue
        if not isinstance(value, str) or not value.strip():
            issue("metadata.string", f"{key} must be a nonblank string (quote timestamps and hashes)")
            continue
        if key == "title" and ("\n" in value or "\r" in value or any(ord(char) < 32 for char in value)):
            issue("metadata.title", "title must be a single-line plain-text string")
        if key in ENUMS and value not in ENUMS[key]:
            issue("metadata.enum", f"{key} must be one of: " + ", ".join(sorted(ENUMS[key])))
        if key in DATE_FIELDS | HASH_FIELDS | REF_FIELDS | LINK_FIELDS:
            if nodes[key].style not in {"'", '"'}:
                issue("metadata.quote", f"{key} must be a quoted YAML string")
        if key in HASH_FIELDS and not re.fullmatch(r"[0-9a-f]+", value):
            issue("metadata.hash", f"{key} must be a lowercase hexadecimal Git object ID")
        if key in DATE_FIELDS:
            try:
                if not RFC3339.fullmatch(value):
                    raise ValueError("expected RFC 3339 timestamp with timezone")
                dates[key] = datetime.fromisoformat(value.upper().replace("Z", "+00:00"))
            except ValueError:
                issue("metadata.timestamp", f"{key} must be a quoted RFC 3339 timestamp with valid date and timezone")
        if key in REF_FIELDS and not _ref_valid(value, short=key == "branch_name"):
            issue("metadata.ref", f"{key} must be a valid Git ref" + (" in short branch form" if key == "branch_name" else ""))
        if key in LINK_FIELDS:
            match = WIKILINK.fullmatch(value)
            if not match or "#" in match[1] or "|" in match[1]:
                issue("metadata.link", f"{key} must be an unaliased wikilink without a heading")
    if dates.get("updated_at") and dates.get("created_at") and dates["updated_at"] < dates["created_at"]:
        issue("metadata.time_order", "updated_at must be at or after created_at")
    if kind in {"project", "repository"} and "repository" in metadata:
        issue("metadata.repository", f"{kind} notes must omit repository")
    if metadata.get("status") == "superseded" and "superseded_by" not in metadata:
        issue("metadata.supersession", "superseded notes require superseded_by")
    if kind == "handoff" and ({"head_commit", "branch_name"} & metadata.keys()) and "repository" not in metadata:
        issue("metadata.repository", "handoff branch_name/head_commit requires repository")
    if kind == "guide" and "verified_commit" in metadata and "repository" not in metadata:
        issue("metadata.repository", "verified_commit requires repository")
    if kind == "merge":
        before, after, source = (metadata.get(key) for key in ("target_before", "target_after", "source_commit"))
        if isinstance(before, str) and before == after:
            issue("merge.noop", "target_before and target_after must differ; no-op is not an integration")
        if metadata.get("merge_kind") == "fast_forward" and source != after:
            issue("merge.fast_forward", "fast_forward target_after must equal source_commit")
        if metadata.get("merge_kind") == "merge_commit" and isinstance(after, str) and after == source:
            issue("merge.result", "merge_commit must record its new merge commit, distinct from the source tip")

    body = "\n".join(lines[closing + 1:])
    visible = _visible_markdown(body)
    note = _Note(path, metadata)
    body_lines = body.splitlines()
    visible_lines = visible.splitlines()
    first = next((line for line in body_lines if line.strip()), "")
    if first != "# " + str(metadata.get("title", "")):
        issue("body.title", "First nonblank body line must be # followed by the exact title")
    headings = []
    for index, line in enumerate(visible_lines):
        match = HEADING.match(line)
        if match:
            title = re.sub(r"[ \t]+#+[ \t]*$", "", match[2])
            note.headings.add(title)
            headings.append((index, len(match[1]), title))
    if sum(level == 1 for _, level, _ in headings) != 1:
        issue("body.h1", "Body must have exactly one H1 outside fenced code")
    h2s = [(index, title) for index, level, title in headings if level == 2]
    for position, (index, title) in enumerate(h2s):
        end = h2s[position + 1][0] if position + 1 < len(h2s) else len(body_lines)
        note.sections.setdefault(title, []).append("\n".join(body_lines[index + 1:end]))
    for title in (*sections, "Related notes"):
        values = note.sections.get(title, [])
        if len(values) != 1:
            issue("body.section", f"Required H2 section {title!r} must occur exactly once")
        elif not _meaningful(values[0]):
            issue("body.empty_section", f"Required H2 section {title!r} needs meaningful content, not an empty/TODO placeholder")
    for match in WIKILINK.finditer(visible):
        note.links.append(_link_parts(match[1]))
    for key in LINK_FIELDS:
        value = metadata.get(key)
        match = WIKILINK.fullmatch(value) if isinstance(value, str) else None
        if match:
            note.links.append(_link_parts(match[1]))
    related = note.sections.get("Related notes", [])
    if len(related) == 1 and not WIKILINK.search(_visible_markdown(related[0])):
        issue("body.related", "Related notes must contain at least one internal wikilink outside code")
    return note


# Extract actual wikilink destinations from a named body section.
def _section_targets(note: _Note, section: str) -> set[str]:
    return { _link_parts(match[1])[0]
             for text in note.sections.get(section, [])
             for match in WIKILINK.finditer(_visible_markdown(text)) }


# Extract the destination of a wikilink-valued metadata field.
def _metadata_target(note: _Note, key: str) -> str | None:
    value = note.metadata.get(key)
    match = WIKILINK.fullmatch(value) if isinstance(value, str) else None
    return _link_parts(match[1])[0] if match else None


# Validate project identity, links, ownership, deduplication, and replacement chains.
def _cross_validate(notes: dict[str, _Note], expected_project_id: str | None,
                    issues: list[ValidationIssue]) -> None:
    # Attach a cross-note diagnostic to the note that contains the problem.
    def issue(note, code, message):
        issues.append(ValidationIssue(note.path, code, message))

    projects = {note.metadata.get("project_id") for note in notes.values()
                if isinstance(note.metadata.get("project_id"), str)}
    identities: dict[tuple, str] = {}
    active_projects = []
    for target, note in sorted(notes.items()):
        data = note.metadata
        kind = data["type"]
        project = data.get("project_id")
        if expected_project_id is not None and project != expected_project_id:
            issue(note, "scope.project", f"project_id must match expected project {expected_project_id!r}")
        elif len(projects) > 1:
            issue(note, "scope.project", "All notes in one vault must share the same project_id")
        for destination, heading in note.links:
            problem = _path_problem(destination)
            if problem or destination.endswith(".md"):
                issue(note, "link.path", f"Invalid wikilink target {destination!r}: {problem or 'omit the .md extension'}")
                continue
            other = notes.get(destination)
            if other is None:
                issue(note, "link.missing", f"Wikilink target does not resolve: {destination}")
            elif destination == target:
                issue(note, "link.self", f"Notes must not link to themselves: {destination}")
            elif other.metadata.get("project_id") != project:
                issue(note, "link.scope", f"Wikilink crosses project scope: {destination}")
            elif heading is not None and heading not in other.headings:
                issue(note, "link.heading", f"Heading {heading!r} does not exist in {destination}")
        repository_target = _metadata_target(note, "repository")
        repository_note = notes.get(repository_target)
        if repository_target is not None and repository_note and repository_note.metadata["type"] != "repository":
            issue(note, "link.repository", "repository must link to a repository note")
        related = _section_targets(note, "Related notes")
        if repository_target is not None and repository_target not in related:
            issue(note, "body.ownership", "Related notes must link to the owning repository")
        if kind == "project":
            repositories = _section_targets(note, "Repositories")
            if not any(path in notes and notes[path].metadata["type"] == "repository" for path in repositories):
                issue(note, "body.repositories", "Repositories must link to at least one repository note")
            if not any(path in notes and notes[path].metadata["type"] == "repository" for path in related):
                issue(note, "body.ownership", "Project Related notes must link to a repository note")
            if data.get("status") == "active":
                active_projects.append(note)
        elif kind == "repository" or repository_target is None:
            if not any(path in notes and notes[path].metadata["type"] == "project" for path in related):
                issue(note, "body.ownership", "Related notes must link to the owning project")
        repository_id = repository_note.metadata.get("id") if repository_note else repository_target
        keys = [("id", data.get("id"))]
        if kind == "repository" and data.get("status") == "active":
            keys.append(("repository", data.get("repository_key")))
        if kind == "branch" and data.get("status") == "active":
            keys.append(("branch", repository_id, data.get("branch_name")))
        if kind == "commit":
            keys.append(("commit", repository_id, data.get("commit_hash")))
        if kind in {"merge", "push"}:
            keys.append(("source_event_id", data.get("source_event_id")))
        for key in keys:
            if any(not isinstance(part, str) or not part for part in key):
                continue
            if key in identities:
                issue(note, "identity.duplicate", f"Duplicate {key[0]} identity; already used by {identities[key]}")
            else:
                identities[key] = note.path
    if len(active_projects) != 1:
        issues.append(ValidationIssue(".", "identity.project", "Vault must have exactly one active project overview"))
    # A replacement chain must terminate rather than circle back to old context.
    for target, note in sorted(notes.items()):
        seen = {target}
        current = note
        while current.metadata.get("status") == "superseded":
            replacement = _metadata_target(current, "superseded_by")
            if replacement in seen:
                issue(note, "lifecycle.cycle", "superseded_by replacement links must not form a cycle")
                break
            if replacement not in notes:
                break
            seen.add(replacement)
            current = notes[replacement]


# Validate a complete local project vault and return deterministic diagnostics.
def validate_vault(vault_root: str | Path, *,
                   expected_project_id: str | None = None) -> list[ValidationIssue]:
    """Validate files and local relations, without modifying or contacting anything."""
    issues: list[ValidationIssue] = []
    try:
        root = Path(vault_root)
        if root.is_symlink() or not root.is_dir():
            return [ValidationIssue(".", "vault.root", "Vault root must be an existing nonsymlink directory")]
    except (OSError, TypeError, ValueError) as error:
        return [ValidationIssue(".", "vault.root", f"Invalid vault root: {error}")]
    notes = {}
    markdown_count = 0

    # Traverse regular notes in sorted order while refusing symlink escapes.
    def visit(directory: Path):
        nonlocal markdown_count
        try:
            with os.scandir(directory) as entries:
                children = sorted(entries, key=lambda entry: entry.name)
        except OSError as error:
            issues.append(ValidationIssue(directory.relative_to(root).as_posix(), "vault.read", f"Cannot read directory: {error}"))
            return
        for entry in children:
            if entry.name == ".obsidian":
                continue
            file = Path(entry.path)
            path = file.relative_to(root).as_posix()
            try:
                if entry.is_symlink():
                    if file.suffix == ".md" or entry.is_dir() or not file.exists():
                        issues.append(ValidationIssue(path, "file.symlink", "Symlinked Markdown notes/directories are not allowed"))
                    continue
                if entry.is_dir(follow_symlinks=False):
                    visit(file)
                elif file.suffix == ".md":
                    markdown_count += 1
                    problem = _path_problem(path)
                    if problem:
                        issues.append(ValidationIssue(path, "file.path", problem))
                    if not entry.is_file(follow_symlinks=False):
                        issues.append(ValidationIssue(path, "file.type", "Markdown notes must be regular files"))
                        continue
                    note = _read_note(file, path, issues)
                    if note:
                        notes[path[:-3]] = note
            except (OSError, ValueError) as error:
                issues.append(ValidationIssue(path, "file.read", f"Cannot inspect note: {error}"))

    visit(root)
    if markdown_count == 0:
        issues.append(ValidationIssue(".", "vault.empty", "Vault contains no Markdown notes"))
    if notes:
        _cross_validate(notes, expected_project_id, issues)
    return sorted(set(issues), key=lambda issue: (issue.path, issue.code, issue.message))


# Run the public CLI and render issues in text or JSON with documented exit codes.
def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("vault_root", type=Path, help="Complete project Markdown vault to validate")
    parser.add_argument("--project-id", dest="expected_project_id", help="Expected authenticated project identity")
    parser.add_argument("--json", action="store_true", help="Emit a JSON array of validation issues")
    args = parser.parse_args(argv)
    issues = validate_vault(args.vault_root, expected_project_id=args.expected_project_id)
    if args.json:
        print(json.dumps([asdict(issue) for issue in issues], ensure_ascii=True))
    elif issues:
        for issue in issues:
            print(f"{issue.path}: {issue.code}: {issue.message}")
        print(f"Structural validation failed: {len(issues)} issue(s).")
    else:
        print("Structural and local cross-note validation passed; source claims were not verified.")
    return 1 if issues else 0


if __name__ == "__main__":
    sys.exit(main())
