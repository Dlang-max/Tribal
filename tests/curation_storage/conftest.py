"""Independent protocol doubles and the complete eleven-note specification graph."""
import copy
from contextlib import contextmanager
import importlib
from pathlib import Path
import re
import sys
import threading

import pytest
import pytest_asyncio

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src/tribal-mcp-server"))
SPEC_ROOT = ROOT / "agent-knowledge-base/specs/v1"
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


# Load every published example without reproducing production note parsing.
@pytest.fixture
def documents():
    result = {}
    for kind, path in NOTE_PATHS.items():
        spec = (SPEC_ROOT / f"{kind}-note.md").read_text()
        match = re.search(r"^(`{3,})markdown\n(.*?)^\1\s*$", spec, re.M | re.S)
        assert match, f"Missing canonical example for {kind}"
        result[path] = match.group(2)
    return result


# Create the complete batch needed to resolve all example cross-note links.
@pytest.fixture
def changes(documents):
    return [{"action": "create", "path": path, "markdown": text}
            for path, text in documents.items()]


class ObjectMemory:
    # Keep exact immutable bytes and observable storage operations.
    def __init__(self):
        self.objects = {}
        self.reads = []
        self.fail_put_at = None
        self.put_count = 0

    # Store one immutable version or simulate a storage outage.
    def put(self, key, content):
        self.put_count += 1
        if self.put_count == self.fail_put_at:
            raise OSError("controlled object-store outage")
        assert isinstance(content, bytes)
        assert key not in self.objects, "An immutable history object was overwritten"
        self.objects[key] = content

    # Rehydrate one exact stored Markdown version.
    def get(self, key):
        self.reads.append(key)
        return self.objects[key]


class CatalogTransaction:
    # Snapshot one project's manifest and replay state for atomic publication.
    def __init__(self, catalog, project_id):
        self.catalog = catalog
        self.project_id = project_id
        self.notes = copy.deepcopy(catalog.notes.get(project_id, {}))
        self.receipts = copy.deepcopy(catalog.receipts.get(project_id, {}))
        self.pending_history = []

    # Return a detached current manifest for whole-vault validation.
    def list_notes(self):
        return copy.deepcopy(list(self.notes.values()))

    # Stage one immutable manifest revision for transaction commit.
    def put_note(self, note):
        self.notes[note["id"]] = copy.deepcopy(note)
        self.pending_history.append(copy.deepcopy(note))

    # Resolve replay identity and reject a changed payload hash.
    def get_request_result(self, request_id, request_hash):
        stored = self.receipts.get(request_id)
        if stored is None:
            return None
        if stored[0] != request_hash:
            raise ValueError("request_id payload hash conflict")
        return copy.deepcopy(stored[1])

    # Preserve the first replay result just as the production SQL transaction does.
    def remember_request_result(self, request_id, request_hash, result):
        if self.get_request_result(request_id, request_hash) is None:
            self.receipts[request_id] = (request_hash, copy.deepcopy(result))


class CatalogMemory:
    # Track project-scoped manifests, history, chunks, and replay receipts.
    def __init__(self):
        self.notes = {}
        self.receipts = {}
        self.chunks = {}
        self.history = []
        self.lock = threading.RLock()
        self.fail_commit = False
        self.replace_attempts = []

    # Serialize proposed-vault publication and roll back exceptions.
    @contextmanager
    def publication(self, project_id):
        with self.lock:
            transaction = CatalogTransaction(self, project_id)
            yield transaction
            if self.fail_commit:
                raise OSError("controlled manifest commit outage")
            self.notes[project_id] = transaction.notes
            self.receipts[project_id] = transaction.receipts
            self.history.extend(transaction.pending_history)

    # Read a detached current project manifest.
    def list_notes(self, project_id):
        with self.lock:
            return copy.deepcopy(list(self.notes.get(project_id, {}).values()))

    # Retrieve durable project-scoped replay information.
    def get_request_result(self, project_id, request_id, request_hash):
        with self.lock:
            return CatalogTransaction(self, project_id).get_request_result(request_id, request_hash)

    # Persist an explicit terminal replay outcome.
    def remember_request_result(self, project_id, request_id, request_hash, result):
        with self.publication(project_id) as transaction:
            transaction.remember_request_result(request_id, request_hash, result)

    # Attach only chunks whose source revision is still current.
    def replace_chunks(self, project_id, note_id, revision, chunks):
        with self.lock:
            self.replace_attempts.append((project_id, note_id, revision))
            note = self.notes.get(project_id, {}).get(note_id)
            if note is None or note["revision"] != revision:
                return False
            self.chunks[(project_id, note_id)] = copy.deepcopy(chunks)
            return True

    # Read search candidates without leaking vectors from another project.
    def list_chunks(self, project_id):
        with self.lock:
            return copy.deepcopy([chunk for (project, _), chunks in self.chunks.items()
                                  if project == project_id for chunk in chunks])


# Inject documented protocols while keeping production adapters separately tested.
@pytest_asyncio.fixture
async def make_service():
    module = importlib.import_module("tribal_kb.service")
    services = []

    # Construct another service instance over chosen shared backing adapters.
    def make(project_id="checkout-demo", objects=None, catalog=None, embedding=None):
        objects = objects if objects is not None else ObjectMemory()
        catalog = catalog if catalog is not None else CatalogMemory()
        service = module.KnowledgeBaseService(
            project_id, objects, catalog, embedding_client=embedding,
            spec_root=SPEC_ROOT,
            validator_path=ROOT / "agent-knowledge-base/validation/v1/validate_knowledge_base_notes.py",
        )
        services.append(service)
        return service, objects, catalog

    yield make
    for service in services:
        await service.drain_indexing()
