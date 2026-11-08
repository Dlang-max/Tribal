"""Persist immutable SeaweedFS objects and transactional MySQL revision manifests."""

from __future__ import annotations

from contextlib import contextmanager
import hashlib
import json

import boto3
import pymysql


# Encode structured catalog values without permitting nonfinite JSON numbers.
def _json(value):
    return json.dumps(value, ensure_ascii=False, allow_nan=False)


# Read JSON returned either as a native value or a MySQL text column.
def _decode(value):
    return json.loads(value) if isinstance(value, (str, bytes)) else value


class SeaweedObjectStore:
    # Configure an S3-compatible SeaweedFS bucket without creating infrastructure.
    def __init__(self, bucket, *, endpoint_url=None, access_key=None, secret_key=None,
                 region="us-east-1", client=None):
        self.bucket = bucket
        self.client = client if client is not None else boto3.client(
            "s3", endpoint_url=endpoint_url, aws_access_key_id=access_key,
            aws_secret_access_key=secret_key, region_name=region)

    # Write a versioned Markdown object before its manifest becomes visible.
    def put(self, key: str, content: bytes) -> None:
        self.client.put_object(Bucket=self.bucket, Key=key, Body=content,
                               ContentType="text/markdown; charset=utf-8")

    # Retrieve the exact published UTF-8 source bytes from SeaweedFS.
    def get(self, key: str) -> bytes:
        response = self.client.get_object(Bucket=self.bucket, Key=key)
        body = response["Body"]
        try:
            return body.read()
        finally:
            body.close()


class _Publication:
    # Bind one project to an already locked SQL publication transaction.
    def __init__(self, cursor, project_id):
        self.cursor = cursor
        self.project_id = project_id

    # Load only the current manifest records belonging to this project.
    def list_notes(self):
        self.cursor.execute("SELECT data FROM tribal_notes WHERE project_id=%s",
                            (self.project_id,))
        return [_decode(row[0]) for row in self.cursor.fetchall()]

    # Publish the new manifest while preserving the previous immutable history.
    def put_note(self, note):
        self.cursor.execute(
            "INSERT INTO tribal_revisions (project_id,note_id,revision,data) VALUES (%s,%s,%s,%s)",
            (self.project_id, note["id"], note["revision"], _json(note)))
        self.cursor.execute(
            "INSERT INTO tribal_notes (project_id,note_id,path_hash,data) VALUES (%s,%s,%s,%s) "
            "ON DUPLICATE KEY UPDATE data=VALUES(data)",
            (self.project_id, note["id"], hashlib.sha256(note["path"].encode()).hexdigest(),
             _json(note)))
        self.cursor.execute("DELETE FROM tribal_chunks WHERE project_id=%s AND note_id=%s",
                            (self.project_id, note["id"]))

    # Resolve a replay receipt and reject reuse with a different payload hash.
    def get_request_result(self, request_id, request_hash):
        self.cursor.execute(
            "SELECT request_hash,result FROM tribal_receipts WHERE project_id=%s AND request_id=%s",
            (self.project_id, request_id))
        row = self.cursor.fetchone()
        if row is None:
            return None
        if row[0] != request_hash:
            raise ValueError("Request ID has already been used with a different payload")
        return _decode(row[1])

    # Preserve the actual published result in the same transaction as its notes.
    def remember_request_result(self, request_id, request_hash, result):
        existing = self.get_request_result(request_id, request_hash)
        if existing is not None:
            return
        self.cursor.execute(
            "INSERT INTO tribal_receipts (project_id,request_id,request_hash,result) "
            "VALUES (%s,%s,%s,%s)", (self.project_id, request_id, request_hash, _json(result)))


class MySQLCatalog:
    # Configure fresh SQL connections and optionally create the minimal catalog tables.
    def __init__(self, *, host="127.0.0.1", port=3306, user="root", password="",
                 database="tribal", connection_factory=None, initialize=True):
        self.connection_factory = connection_factory
        self.connection_options = dict(host=host, port=port, user=user, password=password,
                                       database=database, charset="utf8mb4", autocommit=False)
        if initialize:
            self.initialize()

    # Open a distinct connection for each operation so concurrent runs share no cursor.
    def _connect(self):
        if self.connection_factory is not None:
            return self.connection_factory()
        return pymysql.connect(**self.connection_options)

    # Create durable current notes, history, derived chunks, and replay receipts.
    def initialize(self):
        statements = (
            "CREATE TABLE IF NOT EXISTS tribal_projects (project_id VARCHAR(255) PRIMARY KEY) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_bin",
            "CREATE TABLE IF NOT EXISTS tribal_notes (project_id VARCHAR(255) NOT NULL, "
            "note_id VARCHAR(255) NOT NULL,path_hash CHAR(64) NOT NULL,data JSON NOT NULL,"
            "PRIMARY KEY(project_id,note_id),UNIQUE KEY(project_id,path_hash)) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_bin",
            "CREATE TABLE IF NOT EXISTS tribal_revisions (project_id VARCHAR(255) NOT NULL,"
            "note_id VARCHAR(255) NOT NULL,revision BIGINT NOT NULL,data JSON NOT NULL,"
            "PRIMARY KEY(project_id,note_id,revision)) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_bin",
            "CREATE TABLE IF NOT EXISTS tribal_chunks (project_id VARCHAR(255) NOT NULL,"
            "note_id VARCHAR(255) NOT NULL,position INT NOT NULL,data JSON NOT NULL,"
            "PRIMARY KEY(project_id,note_id,position)) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_bin",
            "CREATE TABLE IF NOT EXISTS tribal_receipts (project_id VARCHAR(255) NOT NULL,"
            "request_id VARCHAR(255) NOT NULL,request_hash VARCHAR(128) NOT NULL,result JSON NOT NULL,"
            "PRIMARY KEY(project_id,request_id)) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_bin",
        )
        connection = self._connect()
        try:
            with connection.cursor() as cursor:
                for statement in statements:
                    cursor.execute(statement)
            connection.commit()
        finally:
            connection.close()

    # Serialize only publication for one project and roll back any incomplete batch.
    @contextmanager
    def publication(self, project_id):
        connection = self._connect()
        try:
            connection.begin()
            with connection.cursor() as cursor:
                cursor.execute("INSERT INTO tribal_projects (project_id) VALUES (%s) "
                               "ON DUPLICATE KEY UPDATE project_id=VALUES(project_id)",
                               (project_id,))
                cursor.execute("SELECT project_id FROM tribal_projects WHERE project_id=%s FOR UPDATE",
                               (project_id,))
                cursor.fetchone()
                yield _Publication(cursor, project_id)
            connection.commit()
        except BaseException:
            connection.rollback()
            raise
        finally:
            connection.close()

    # Load current manifests through a project-scoped read without taking its write lock.
    def list_notes(self, project_id):
        connection = self._connect()
        try:
            with connection.cursor() as cursor:
                return _Publication(cursor, project_id).list_notes()
        finally:
            connection.close()

    # Read a saved result with the same conflict policy as publication.
    def get_request_result(self, project_id, request_id, request_hash):
        connection = self._connect()
        try:
            with connection.cursor() as cursor:
                return _Publication(cursor, project_id).get_request_result(request_id, request_hash)
        finally:
            connection.close()

    # Save a result while coordinating with note publication and other receipt writers.
    def remember_request_result(self, project_id, request_id, request_hash, result):
        with self.publication(project_id) as transaction:
            transaction.remember_request_result(request_id, request_hash, result)

    # Attach derived chunks only when their source revision is still current.
    def replace_chunks(self, project_id, note_id, revision, chunks):
        with self.publication(project_id) as transaction:
            note = next((n for n in transaction.list_notes() if n["id"] == note_id), None)
            if note is None or note["revision"] != revision:
                return False
            transaction.cursor.execute(
                "DELETE FROM tribal_chunks WHERE project_id=%s AND note_id=%s", (project_id, note_id))
            for chunk in chunks:
                transaction.cursor.execute(
                    "INSERT INTO tribal_chunks (project_id,note_id,position,data) VALUES (%s,%s,%s,%s)",
                    (project_id, note_id, chunk["position"], _json(chunk)))
        return True

    # Read the small project's derived search index for in-memory ranking.
    def list_chunks(self, project_id):
        connection = self._connect()
        try:
            with connection.cursor() as cursor:
                cursor.execute("SELECT data FROM tribal_chunks WHERE project_id=%s", (project_id,))
                return [_decode(row[0]) for row in cursor.fetchall()]
        finally:
            connection.close()
