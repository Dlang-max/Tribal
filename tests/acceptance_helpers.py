"""Synthetic public-contract fixtures shared by independent acceptance tests."""
from __future__ import annotations

import json
import uuid

DOCUMENT_ID = "20000000-0000-4000-8000-000000000001"
REVISION_ID = "30000000-0000-4000-8000-000000000001"


def note(body="A useful observation.\n", **changes):
    metadata = dict(schema_version=1, id=DOCUMENT_ID, title="Seed observations",
                    knowledge_base="fixture-kb", domain="research", kind="finding",
                    summary="A reproducible observation.")
    metadata.update(changes)
    frontmatter = "".join(f"{key}: {json.dumps(value, ensure_ascii=False)}\n"
                          for key, value in metadata.items())
    return f"---\n{frontmatter}---\n{body}"


def distinct_note(body="A useful observation.\n", **changes):
    return note(body, **dict(id=str(uuid.uuid4()), **changes))


def diagnostic_codes(result):
    return {item["code"] for item in result["diagnostics"]}
