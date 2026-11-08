"""Independent fixtures built from the eleven authoritative example documents."""
import importlib
from pathlib import Path
import re
import sys

import pytest


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
SPEC_ROOT = REPOSITORY_ROOT / "agent-knowledge-base/specs/v1"
IMPLEMENTATION_ROOT = REPOSITORY_ROOT / "agent-knowledge-base/validation/v1"
NOTE_PATHS = {
    "project": "Projects/Checkout Platform.md",
    "repository": "Repositories/Checkout Service.md",
    "branch": "Branches/Checkout Discount Validation.md",
    "commit": "Commits/Reject Expired Discounts.md",
    "merge": "Merges/Integrate Discount Validation.md",
    "push": "Pushes/Publish Discount Validation.md",
    "finding": "Findings/Expired Code Accepted.md",
    "insight": "Insights/Validate Discounts Before Totals.md",
    "decision": "Decisions/Server Owns Discount Validation.md",
    "handoff": "Handoffs/Checkout UI Verification.md",
    "guide": "Guides/Run Checkout Checks.md",
}
REQUIRED_SECTIONS = {
    "project": ("Summary", "Repositories", "Working context", "Related notes"),
    "repository": ("Purpose", "Structure", "Working instructions", "Dependencies and connections", "Related notes"),
    "branch": ("Intent", "Progress", "Remaining work", "Related notes"),
    "commit": ("Summary", "Commit message", "Affected files", "Verification", "Related notes"),
    "merge": ("Summary", "Integrated changes", "Conflicts and verification", "Related notes"),
    "push": ("Summary", "Ref updates", "Verification", "Related notes"),
    "finding": ("Observation", "Evidence", "Implications", "Related notes"),
    "insight": ("Insight", "Basis", "Implications", "Related notes"),
    "decision": ("Context", "Decision", "Rationale and alternatives", "Authority", "Consequences", "Related notes"),
    "handoff": ("Goal", "Completed work", "Current state", "Blockers", "Next steps", "Related notes"),
    "guide": ("Purpose and scope", "Prerequisites", "Procedure", "Verification", "Troubleshooting", "Related notes"),
}


# Build a complete temporary vault from the eleven authoritative examples.
@pytest.fixture
def valid_vault(tmp_path):
    vault = tmp_path / "Example Knowledge Base"
    for note_type, relative_path in NOTE_PATHS.items():
        specification = (SPEC_ROOT / f"{note_type}-note.md").read_text()
        match = re.search(r"^(`{3,})markdown\n(.*?)^\1\s*$", specification, re.M | re.S)
        assert match is not None, f"Missing published example for {note_type}"
        path = vault / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(match.group(2), encoding="utf-8")
    return vault


# Load the public validator API from the documented implementation directory.
@pytest.fixture
def validate():
    sys.path.insert(0, str(IMPLEMENTATION_ROOT))
    try:
        module = importlib.import_module("validate_knowledge_base_notes")
        yield module.validate_vault
    finally:
        sys.path.remove(str(IMPLEMENTATION_ROOT))


# Locate the example document for one note type.
def note_path(vault, note_type="finding"):
    return vault / NOTE_PATHS[note_type]


# Set one metadata field while preserving all other document bytes as text.
def set_raw_field(path, field, raw_value):
    text = path.read_text()
    frontmatter, body = text.split("\n---\n", 1)
    line = f"{field}: {raw_value}"
    if re.search(rf"^{re.escape(field)}:.*$", frontmatter, re.M):
        frontmatter = re.sub(rf"^{re.escape(field)}:.*$", lambda _: line, frontmatter, flags=re.M)
    else:
        frontmatter += f"\n{line}"
    path.write_text(frontmatter + "\n---\n" + body)


# Remove one metadata key to exercise an omission or conditional dependency.
def remove_field(path, field):
    text = path.read_text()
    path.write_text(re.sub(rf"^{re.escape(field)}:.*\n", "", text, count=1, flags=re.M))


# Replace one section body while preserving its required heading.
def replace_section(path, heading, content):
    text = path.read_text()
    pattern = rf"(^## {re.escape(heading)}\n).*?(?=^## |\Z)"
    text, count = re.subn(pattern, lambda m: m.group(1) + content + "\n\n", text, count=1, flags=re.M | re.S)
    assert count == 1
    path.write_text(text)


# Require useful validation issues and identify the affected document when supplied.
def assert_rejected(validate, vault, affected_path=None):
    issues = validate(vault)
    assert issues, "Invalid vault was accepted"
    for issue in issues:
        assert all(isinstance(getattr(issue, field), str) and getattr(issue, field).strip()
                   for field in ("path", "code", "message"))
    if affected_path is not None:
        assert any(str(affected_path).endswith(issue.path) or issue.path.endswith(affected_path.name)
                   for issue in issues), issues
    return issues
