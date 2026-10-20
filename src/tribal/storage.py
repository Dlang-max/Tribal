"""MySQL connections, versioned schema, and small registry primitives."""
from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
from importlib.resources import files
import json
import threading
from uuid import UUID, uuid4

import mysql.connector
from tiktoken import list_encoding_names

from .errors import TribalError


DEFAULT_PROFILE_CONFIGURATION = {
    "wrapper": "tribal-title-headings-v1",
    "encoding": "cl100k_base",
    "max_input_tokens": 8192,
    "distance": "cosine",
    "normalization": "l2-float32-v1",
}
_STRICT_MODE = "STRICT_ALL_TABLES,ERROR_FOR_DIVISION_BY_ZERO,NO_ENGINE_SUBSTITUTION"
_MIN_PACKET_BYTES = 64 * 1024 * 1024


class Database:
    """A connection factory; each transaction owns and closes its connection.

    No connection is retained between calls, so separate threads can safely use
    the same factory. Nested transactions in the same thread are unsupported.
    """

    def __init__(self, **connect_options):
        self._options = dict(connect_options)
        self._options.setdefault("use_pure", True)
        self._options.update(autocommit=False, time_zone="+00:00",
                             charset="utf8mb4", collation="utf8mb4_0900_ai_ci",
                             sql_mode=_STRICT_MODE)
        self._local = threading.local()
        self._closed = False

    @contextmanager
    def transaction(self, *, readonly=False):
        """Start explicitly, commit on success, and roll back on any exception."""
        if self._closed:
            raise TribalError("E_DATABASE", "Database factory is closed.",
                              hint="Create a new Database instance.")
        if getattr(self._local, "active", False):
            raise TribalError("E_ARGUMENT", "Nested transactions are unsupported.",
                              hint="Pass the current connection to internal helpers.")
        connection = None
        self._local.active = True
        try:
            connection = mysql.connector.connect(**self._options)
            with connection.cursor() as cursor:
                cursor.execute("SELECT @@session.max_allowed_packet")
                packet_bytes = cursor.fetchone()[0]
            if packet_bytes < _MIN_PACKET_BYTES:
                raise TribalError(
                    "E_DATABASE", "MySQL packet capacity is too small.",
                    expected=_MIN_PACKET_BYTES, actual=packet_bytes,
                    hint="Configure MySQL max_allowed_packet=64M or greater, then reconnect.",
                )
            connection.start_transaction(
                isolation_level="REPEATABLE READ", readonly=readonly,
                consistent_snapshot=readonly,
            )
            yield connection
            connection.commit()
        except BaseException as error:
            if connection is not None:
                try:
                    connection.rollback()
                except mysql.connector.Error:
                    pass
            if isinstance(error, mysql.connector.Error):
                raise TribalError(
                    "E_DATABASE", "MySQL operation failed; transaction rolled back.",
                    hint="Check database availability, configuration, and schema migrations.",
                ) from None
            raise
        finally:
            if connection is not None:
                connection.close()
            self._local.active = False

    def close(self):
        """Prevent new transactions; connections already close on context exit."""
        self._closed = True


def _uuid_bytes(value):
    try:
        identity = UUID(value)
    except (ValueError, TypeError, AttributeError):
        raise TribalError("E_ARGUMENT", "Expected a canonical non-nil UUID.") from None
    if identity.int == 0 or str(identity) != value:
        raise TribalError("E_ARGUMENT", "Expected a canonical non-nil UUID.")
    return identity.bytes


def _row(row):
    """Normalize registry rows without changing generic connector behavior."""
    result = dict(row)
    for key, value in result.items():
        if isinstance(value, (bytes, bytearray)) and (key == "id" or key.endswith("_id")):
            result[key] = str(UUID(bytes=bytes(value)))
        elif isinstance(value, datetime):
            result[key] = value.replace(tzinfo=timezone.utc).isoformat().replace("+00:00", "Z")
        elif key == "configuration" and isinstance(value, (str, bytes, bytearray)):
            result[key] = json.loads(value)
    return result


def _one(connection, statement, parameters=()):
    with connection.cursor(dictionary=True) as cursor:
        cursor.execute(statement, parameters)
        return cursor.fetchone()


def _result(kind, row):
    return {"ok": True, "diagnostics": [], kind: _row(row)}


def lock_knowledge_base(connection, knowledge_base):
    """Acquire the publication gate before any document or derived-data locks."""
    row = _one(connection,
               "SELECT * FROM knowledge_bases WHERE knowledge_base_key=%s FOR UPDATE",
               (knowledge_base,))
    if row is None:
        raise TribalError("E_NOT_FOUND", "Knowledge base is not registered.",
                          hint="Register the knowledge base before using it.")
    return _row(row)


def advance_generations(connection, knowledge_base_id, *, knowledge=False, indexing=False):
    """Increment each requested generation once on an already locked KB."""
    if not knowledge and not indexing:
        return
    with connection.cursor() as cursor:
        cursor.execute(
            "UPDATE knowledge_bases SET knowledge_generation=knowledge_generation+%s, "
            "indexing_generation=indexing_generation+%s WHERE id=%s",
            (int(bool(knowledge)), int(bool(indexing)), _uuid_bytes(knowledge_base_id)),
        )
        if cursor.rowcount != 1:
            raise TribalError("E_NOT_FOUND", "Knowledge base is not registered.")


def _text(value, field, maximum, *, nullable=False):
    if nullable and value is None:
        return
    if not isinstance(value, str) or not value.strip() or len(value) > maximum:
        raise TribalError("E_ARGUMENT", "Registry field is empty or exceeds its capacity.",
                          field=field, expected=f"1..{maximum} characters")


def ensure_knowledge_base(db, *, key, name, description=None):
    _text(key, "key", 128)
    _text(name, "name", 255)
    _text(description, "description", 16383, nullable=True)
    with db.transaction() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                "INSERT INTO knowledge_bases (id,knowledge_base_key,name,description) "
                "VALUES (%s,%s,%s,%s) ON DUPLICATE KEY UPDATE id=id",
                (uuid4().bytes, key, name, description),
            )
        row = lock_knowledge_base(connection, key)
        if row["name"] != name or row["description"] != description or row["knowledge_base_key"] != key:
            raise TribalError("E_CONFLICT", "Knowledge base configuration differs from registration.")
        return {"ok": True, "diagnostics": [], "knowledge_base": row}


def get_knowledge_base(db, *, knowledge_base):
    with db.transaction(readonly=True) as connection:
        row = _one(connection,
                   "SELECT * FROM knowledge_bases WHERE knowledge_base_key=%s",
                   (knowledge_base,))
        if row is None:
            raise TribalError("E_NOT_FOUND", "Knowledge base is not registered.",
                              hint="Register the knowledge base before using it.")
        return _result("knowledge_base", row)


def ensure_domain(db, *, knowledge_base, key, name, description=None):
    _text(key, "key", 128)
    _text(name, "name", 255)
    _text(description, "description", 16383, nullable=True)
    with db.transaction() as connection:
        kb = lock_knowledge_base(connection, knowledge_base)
        kb_id = _uuid_bytes(kb["id"])
        row = _one(connection,
                   "SELECT * FROM domains WHERE knowledge_base_id=%s AND domain_key=%s FOR UPDATE",
                   (kb_id, key))
        if row is None:
            identity = uuid4().bytes
            with connection.cursor() as cursor:
                cursor.execute(
                    "INSERT INTO domains (id,knowledge_base_id,domain_key,name,description) "
                    "VALUES (%s,%s,%s,%s,%s)",
                    (identity, kb_id, key, name, description),
                )
            row = _one(connection, "SELECT * FROM domains WHERE id=%s", (identity,))
        if row["domain_key"] != key or row["name"] != name or row["description"] != description:
            raise TribalError("E_CONFLICT", "Domain configuration differs from registration.")
        return _result("domain", row)


def ensure_profile(db, *, key="openai-text-embedding-3-small-v1", provider="openai",
                   model="text-embedding-3-small", dimensions=1536,
                   configuration=None, model_version=None):
    _text(key, "key", 128)
    _text(provider, "provider", 128)
    _text(model, "model", 255)
    _text(model_version, "model_version", 128, nullable=True)
    if isinstance(dimensions, bool) or not isinstance(dimensions, int) or not 1 <= dimensions <= 16383:
        raise TribalError("E_ARGUMENT", "Embedding dimensions must be an integer from 1 to 16383.")
    if configuration is None:
        if (provider, model, dimensions) != ("openai", "text-embedding-3-small", 1536):
            raise TribalError("E_ARGUMENT", "Nondefault profiles require explicit configuration.")
        configuration = dict(DEFAULT_PROFILE_CONFIGURATION)
    if not isinstance(configuration, dict):
        raise TribalError("E_ARGUMENT", "Profile configuration must be a JSON object.")
    try:
        encoded_configuration = json.dumps(configuration, ensure_ascii=False, allow_nan=False)
    except (TypeError, ValueError):
        raise TribalError("E_ARGUMENT", "Profile configuration must contain JSON values.") from None
    for field, supported in (("wrapper", "tribal-title-headings-v1"),
                             ("distance", "cosine"), ("normalization", "l2-float32-v1")):
        if configuration.get(field) != supported:
            raise TribalError("E_ARGUMENT", "Unsupported embedding profile configuration.",
                              field=f"configuration.{field}", expected=supported)
    encoding = configuration.get("encoding")
    if not isinstance(encoding, str) or encoding not in list_encoding_names():
        raise TribalError("E_ARGUMENT", "Profile encoding must be registered with tiktoken.",
                          field="configuration.encoding")
    limit = configuration.get("max_input_tokens")
    if isinstance(limit, bool) or not isinstance(limit, int) or limit <= 0:
        raise TribalError("E_ARGUMENT", "Profile token limit must be a positive integer.",
                          field="configuration.max_input_tokens")
    if provider == "openai" and model in {"text-embedding-3-small", "text-embedding-3-large"} and limit > 8192:
        raise TribalError("E_ARGUMENT", "The configured model accepts at most 8192 input tokens.",
                          field="configuration.max_input_tokens", expected=8192, actual=limit)
    with db.transaction() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                "INSERT INTO embedding_profiles "
                "(id,profile_key,provider,model,model_version,dimensions,configuration) "
                "VALUES (%s,%s,%s,%s,%s,%s,%s) ON DUPLICATE KEY UPDATE id=id",
                (uuid4().bytes, key, provider, model, model_version, dimensions, encoded_configuration),
            )
        row = _row(_one(connection,
                        "SELECT * FROM embedding_profiles WHERE profile_key=%s FOR UPDATE", (key,)))
        expected = {"profile_key": key, "provider": provider, "model": model,
                    "model_version": model_version, "dimensions": dimensions,
                    "configuration": configuration}
        if any(row[field] != value for field, value in expected.items()):
            raise TribalError("E_CONFLICT", "Embedding profile configuration is immutable.",
                              hint="Create a new profile key for a different configuration.")
        return {"ok": True, "diagnostics": [], "profile": row}


def get_profile(db, *, profile_id=None, key=None):
    if (profile_id is None) == (key is None):
        raise TribalError("E_ARGUMENT", "Provide exactly one of profile_id or key.")
    if profile_id is not None:
        statement, parameters = "SELECT * FROM embedding_profiles WHERE id=%s", (_uuid_bytes(profile_id),)
    else:
        statement, parameters = "SELECT * FROM embedding_profiles WHERE profile_key=%s", (key,)
    with db.transaction(readonly=True) as connection:
        row = _one(connection, statement, parameters)
        if row is None:
            raise TribalError("E_NOT_FOUND", "Embedding profile is not registered.",
                              hint="Register the embedding profile before using it.")
        return _result("profile", row)


def migrate(db):
    """Apply packaged SQL in version order; refuse altered/unknown history.

    MySQL DDL commits implicitly. Each completed file is recorded durably. A
    failed file can leave partial DDL; recover a fresh development database as
    documented instead of treating DDL rollback as transactional.
    """
    migrations = sorted(files("tribal").joinpath("migrations").iterdir(), key=lambda p: p.name)
    migrations = [(path.name.removesuffix(".sql"), path.read_bytes())
                  for path in migrations if path.name.endswith(".sql")]
    known = {version: hashlib.sha256(content).digest() for version, content in migrations}
    applied = []
    try:
        with db.transaction() as connection:
            with connection.cursor(dictionary=True) as cursor:
                cursor.execute("SELECT DATABASE() AS name, VERSION() AS version")
                server = cursor.fetchone()
                if not server["name"] or not server["version"].startswith("9.7."):
                    raise TribalError("E_MIGRATION", "Migrations require a selected MySQL 9.7 database.")
                lock_name = "tribal:migrate:" + hashlib.sha256(server["name"].encode()).hexdigest()[:48]
                cursor.execute("SELECT GET_LOCK(%s, 30) AS acquired", (lock_name,))
                if cursor.fetchone()["acquired"] != 1:
                    raise TribalError("E_MIGRATION", "Another schema migration is running.",
                                      hint="Wait for the other migration and retry.")
                try:
                    cursor.execute(
                        "CREATE TABLE IF NOT EXISTS schema_migrations ("
                        "version VARCHAR(64) PRIMARY KEY, checksum BINARY(32) NOT NULL, "
                        "applied_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6)) ENGINE=InnoDB"
                    )
                    cursor.execute("SELECT version,checksum FROM schema_migrations ORDER BY version")
                    history = {row["version"]: row["checksum"] for row in cursor.fetchall()}
                    if any(version not in known or known[version] != checksum
                           for version, checksum in history.items()):
                        raise TribalError("E_MIGRATION", "Applied migration history does not match packaged migrations.",
                                          hint="Restore matching migration files; do not edit applied migrations.")
                    if list(history) != [version for version, _ in migrations][:len(history)]:
                        raise TribalError("E_MIGRATION", "Applied migrations are not an ordered prefix.")
                    for version, content in migrations:
                        if version in history:
                            continue
                        # Connector's script execution handles DELIMITER and
                        # compound trigger statements, including comments.
                        cursor.execute(content.decode("utf-8"))
                        while cursor.nextset():
                            pass
                        cursor.execute("INSERT INTO schema_migrations (version,checksum) VALUES (%s,%s)",
                                       (version, known[version]))
                        connection.commit()
                        applied.append(version)
                finally:
                    cursor.execute("SELECT RELEASE_LOCK(%s)", (lock_name,))
                    cursor.fetchone()
    except TribalError as error:
        if error.code != "E_DATABASE":
            raise
        raise TribalError("E_MIGRATION", "Schema migration failed; MySQL DDL may be partially applied.",
                          hint="Inspect the schema; recreate a fresh development database before retrying incomplete migrations.") from None
    return {"ok": True, "diagnostics": [], "applied": applied,
            "schema_version": migrations[-1][0] if migrations else None}
