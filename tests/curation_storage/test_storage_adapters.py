"""Check real S3 and MySQL adapters through controlled external-library boundaries."""
from io import BytesIO
import importlib
import json

import boto3
from botocore.exceptions import ClientError
from botocore.response import StreamingBody
from botocore.stub import Stubber
import pytest


# Load only the documented production storage adapter classes.
def storage_module():
    return importlib.import_module("tribal_kb.storage")


# Use botocore's operation schema to verify exact bytes and bucket/key routing.
def test_seaweed_s3_put_and_get_use_markdown_bytes_and_close_stream():
    client = boto3.client("s3", region_name="us-east-1", aws_access_key_id="test", aws_secret_access_key="test")
    raw = BytesIO("# Exact UTF-8 source — preserved\n".encode())
    body = StreamingBody(raw, len(raw.getvalue()))
    source = raw.getvalue()
    with Stubber(client) as stubber:
        stubber.add_response("put_object", {}, {
            "Bucket": "tribal-notes", "Key": "project/version.md", "Body": source,
            "ContentType": "text/markdown; charset=utf-8",
        })
        stubber.add_response("get_object", {"Body": body}, {
            "Bucket": "tribal-notes", "Key": "project/version.md",
        })
        store = storage_module().SeaweedObjectStore("tribal-notes", client=client)
        store.put("project/version.md", source)
        assert store.get("project/version.md") == source
        assert raw.closed
        stubber.assert_no_pending_responses()


# Preserve dependency failures so missing source cannot masquerade as an empty note.
def test_seaweed_s3_dependency_errors_propagate():
    client = boto3.client("s3", region_name="us-east-1", aws_access_key_id="test", aws_secret_access_key="test")
    with Stubber(client) as stubber:
        stubber.add_client_error("get_object", service_error_code="NoSuchKey", http_status_code=404,
                                 expected_params={"Bucket": "tribal-notes", "Key": "missing.md"})
        store = storage_module().SeaweedObjectStore("tribal-notes", client=client)
        with pytest.raises(ClientError):
            store.get("missing.md")
        stubber.assert_no_pending_responses()


class ControlledCursor:
    # Record bound SQL parameters and route SELECT responses through a controlled boundary.
    def __init__(self, connection):
        self.connection = connection
        self.rows = []

    # Return the cursor as a normal PyMySQL context manager.
    def __enter__(self):
        return self

    # Close the cursor context without suppressing database failures.
    def __exit__(self, *args):
        self.connection.events.append(("cursor_close",))

    # Accept bound statements and surface configured database failures.
    def execute(self, statement, parameters=None):
        self.connection.events.append(("execute", statement, parameters))
        if self.connection.responder is not None:
            self.rows = self.connection.responder(statement, parameters) or []
        else:
            self.rows = []
        return len(self.rows)

    # Return one database result row using the standard driver shape.
    def fetchone(self):
        return self.rows[0] if self.rows else None

    # Return all database result rows using the standard driver shape.
    def fetchall(self):
        return list(self.rows)


class ControlledConnection:
    # Observe transaction lifecycle and inject real driver-shaped result tuples.
    def __init__(self, responder=None, fail_commit=False):
        self.events = []
        self.responder = responder
        self.fail_commit = fail_commit

    # Open a fresh cursor over this controlled connection.
    def cursor(self):
        return ControlledCursor(self)

    # Record when the adapter begins its transaction.
    def begin(self):
        self.events.append(("begin",))

    # Commit staged work or emulate an interrupted commit.
    def commit(self):
        self.events.append(("commit",))
        if self.fail_commit:
            raise OSError("controlled SQL commit failure")

    # Record rollback of all staged publication work.
    def rollback(self):
        self.events.append(("rollback",))

    # Mark this connection closed so cleanup can be asserted.
    def close(self):
        self.events.append(("close",))


# Construct a catalog whose connections remain fully observable to these tests.
def controlled_catalog(responder=None, fail_commit=False, initialize=False):
    connections = []

    # Supply the fresh PyMySQL-compatible connection required for each operation.
    def connect():
        connection = ControlledConnection(responder, fail_commit=fail_commit)
        connections.append(connection)
        return connection

    catalog = storage_module().MySQLCatalog(connection_factory=connect, initialize=initialize)
    return catalog, connections


# Verify lock acquisition precedes catalog reads, all data are bound, and publication commits once.
def test_mysql_publication_locks_project_and_atomically_records_history_manifest_receipt():
    project = "project'; DROP TABLE tribal_notes; --"
    note = {"id": "note'quoted", "path": "Findings/Quoted Note.md", "revision": 1,
            "object_key": "immutable.md", "title": "A quoted title", "type": "finding",
            "status": "active", "content_hash": "abc"}
    result = {"status": "updated", "notes": [{"path": note["path"], "action": "created"}]}
    catalog, connections = controlled_catalog()
    with catalog.publication(project) as transaction:
        assert transaction.list_notes() == []
        transaction.put_note(note)
        transaction.remember_request_result("request'quoted", "hash'quoted", result)
    events = connections[0].events
    executions = [event for event in events if event[0] == "execute"]
    lock_position = next(i for i, event in enumerate(executions) if "FOR UPDATE" in event[1])
    manifest_position = next(i for i, event in enumerate(executions) if event[1].startswith("SELECT data"))
    assert lock_position < manifest_position
    assert all(project not in event[1] and note["id"] not in event[1] for event in executions)
    assert all(event[2] is not None and project in event[2] for event in executions)
    inserts = [event for event in executions if event[1].startswith("INSERT")]
    assert any(note["id"] in event[2] and note["revision"] in event[2] for event in inserts)
    assert any(any(isinstance(value, str) and '"object_key"' in value for value in event[2]) for event in inserts)
    assert any("request'quoted" in event[2] and "hash'quoted" in event[2] for event in inserts)
    assert [event[0] for event in events].count("commit") == 1
    assert not any(event[0] == "rollback" for event in events)
    assert events[-1] == ("close",)


# Roll back driver failures during work and during commit without reporting success.
@pytest.mark.parametrize("during_commit", [False, True])
def test_mysql_publication_failure_rolls_back_and_closes(during_commit):
    catalog, connections = controlled_catalog(fail_commit=during_commit)
    with pytest.raises(OSError):
        with catalog.publication("checkout-demo"):
            if not during_commit:
                raise OSError("controlled interrupted transaction")
    events = connections[0].events
    assert ("rollback",) in events
    assert events[-1] == ("close",)
    if not during_commit:
        assert ("commit",) not in events


# Deserialize note JSON while keeping project scope in the bound SELECT parameters.
def test_mysql_catalog_read_scoping_json_rehydration_and_fresh_connections():
    note = {"id": "n", "path": "Findings/A Note.md", "revision": 3}

    # Return catalog rows as MySQL's JSON text output.
    def respond(statement, parameters):
        if statement.startswith("SELECT data"):
            return [(json.dumps(note),)]
        return []

    catalog, connections = controlled_catalog(respond)
    assert catalog.list_notes("project-a") == [note]
    assert catalog.list_notes("project-b") == [note]
    assert len(connections) == 2
    for project, connection in zip(("project-a", "project-b"), connections):
        query = next(event for event in connection.events if event[0] == "execute")
        assert query[2] == (project,)
        assert project not in query[1]
        assert connection.events[-1] == ("close",)


# Resolve saved request JSON and reject a conflicting hash from real adapter code.
def test_mysql_receipts_decode_and_enforce_hash():
    result = {"status": "updated", "notes": [{"path": "A.md", "action": "created"}]}

    # Simulate a durable receipt returned by a MySQL result cursor.
    def respond(statement, parameters):
        if statement.startswith("SELECT request_hash"):
            return [("original-hash", json.dumps(result))]
        return []

    catalog, connections = controlled_catalog(respond)
    assert catalog.get_request_result("p", "request", "original-hash") == result
    with pytest.raises(ValueError):
        catalog.get_request_result("p", "request", "changed-hash")
    assert all(connection.events[-1] == ("close",) for connection in connections)


# Reject stale vector work before deleting or inserting current derived chunks.
@pytest.mark.parametrize("revision,expected", [(2, False), (3, True)])
def test_mysql_chunk_compare_and_set_preserves_current_revision(revision, expected):
    manifest = {"id": "n", "path": "A.md", "revision": 3}

    # Return a currently published manifest with a newer source revision.
    def respond(statement, parameters):
        if statement.startswith("SELECT data"):
            return [(json.dumps(manifest),)]
        return []

    catalog, connections = controlled_catalog(respond)
    chunk = {"note_id": "n", "revision": revision, "position": 0, "heading": "Overview",
             "text": "hello", "content_hash": "hash", "model": "m", "dimensions": 2, "vector": [1.0, 0.0]}
    assert catalog.replace_chunks("p", "n", revision, [chunk]) is expected
    statements = [event for event in connections[0].events if event[0] == "execute"]
    mutations = [event for event in statements if event[1].startswith(("DELETE", "INSERT INTO tribal_chunks"))]
    if expected:
        assert any(event[1].startswith("DELETE") for event in mutations)
        assert any(json.dumps(chunk) in event[2] for event in mutations)
    else:
        assert mutations == []
    assert connections[0].events[-1] == ("close",)


# Initialize transactional, case-sensitive tables through the actual schema adapter.
def test_mysql_initialization_uses_transactional_case_sensitive_tables():
    _, connections = controlled_catalog(initialize=True)
    schema = [event[1] for event in connections[0].events if event[0] == "execute"]
    assert len(schema) == 5
    assert all(statement.startswith("CREATE TABLE IF NOT EXISTS") for statement in schema)
    assert all("InnoDB" in statement and "utf8mb4_0900_bin" in statement for statement in schema)
    assert ("commit",) in connections[0].events
    assert connections[0].events[-1] == ("close",)


# Require NO PAD key comparison so opaque identifiers differing by trailing space stay distinct.
def test_mysql_schema_preserves_trailing_space_in_opaque_identifiers():
    _, connections = controlled_catalog(initialize=True)
    schema = [event[1] for event in connections[0].events if event[0] == "execute"]
    # MySQL 8's 0900 binary collation is NO PAD; older utf8mb4_bin is PAD SPACE.
    assert all("utf8mb4_0900_bin" in statement or "VARBINARY" in statement.upper() for statement in schema), (
        "Opaque project/note/request IDs require NO PAD collation or binary key storage"
    )
