"""Real MySQL checks: no transaction or vector-storage substitutes."""
from __future__ import annotations

import json
import struct
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor

import pytest

pytestmark = pytest.mark.mysql


def sql(db, statement, params=()):
    with db.transaction() as connection:
        cursor = connection.cursor(dictionary=True)
        try:
            cursor.execute(statement, params)
            return cursor.fetchall() if cursor.with_rows else cursor.rowcount
        finally:
            cursor.close()


def test_migrations_are_executable_idempotent_and_record_exact_checksums(mysql_db):
    from tribal.storage import migrate
    first = migrate(mysql_db)
    assert first["ok"] is True
    assert first["applied"] == []
    rows = sql(mysql_db, "SELECT version, checksum FROM schema_migrations ORDER BY version")
    assert rows
    assert first["schema_version"] == rows[-1]["version"]
    assert all(isinstance(row["checksum"], bytes) and len(row["checksum"]) == 32 for row in rows)
    assert migrate(mysql_db)["applied"] == []


def test_migration_checksum_tampering_is_refused(mysql_db):
    from tribal.errors import TribalError
    from tribal.storage import migrate
    row = sql(mysql_db, "SELECT version, checksum FROM schema_migrations ORDER BY version LIMIT 1")[0]
    try:
        sql(mysql_db, "UPDATE schema_migrations SET checksum=%s WHERE version=%s", (b"\x00" * 32, row["version"]))
        with pytest.raises(TribalError) as failure:
            migrate(mysql_db)
        assert failure.value.code == "E_MIGRATION"
    finally:
        sql(mysql_db, "UPDATE schema_migrations SET checksum=%s WHERE version=%s", (row["checksum"], row["version"]))


def test_all_content_job_and_session_tables_use_innodb(mysql_db):
    rows = sql(mysql_db, "SELECT TABLE_NAME, ENGINE FROM information_schema.TABLES WHERE TABLE_SCHEMA=DATABASE()")
    engines = {row["TABLE_NAME"]: row["ENGINE"] for row in rows}
    required = {"knowledge_bases", "domains", "documents", "document_revisions", "document_sources",
                "document_links", "document_chunks", "embedding_profiles", "chunk_embeddings",
                "schema_migrations", "embedding_jobs", "search_sessions", "search_session_results"}
    assert required <= engines.keys()
    assert all(engines[table] == "InnoDB" for table in required)
    vectors = sql(mysql_db, "SELECT TABLE_NAME, COLUMN_NAME, DATA_TYPE FROM information_schema.COLUMNS WHERE TABLE_SCHEMA=DATABASE() AND DATA_TYPE='vector'")
    assert {("chunk_embeddings", "embedding"), ("search_sessions", "query_vector")} <= {
        (r["TABLE_NAME"], r["COLUMN_NAME"]) for r in vectors}


def test_connections_enforce_utc_strict_utf8_explicit_transaction(mysql_db):
    row = sql(mysql_db, "SELECT @@session.time_zone AS tz, @@session.autocommit AS ac, @@session.character_set_connection AS charset, @@session.sql_mode AS modes")[0]
    assert row["tz"] == "+00:00"
    assert row["ac"] == 0
    assert row["charset"] == "utf8mb4"
    assert {"STRICT_TRANS_TABLES", "STRICT_ALL_TABLES"}.intersection(row["modes"].split(","))


def test_transactions_commit_and_rollback_real_rows(mysql_db):
    identity = uuid.uuid4().bytes
    key = "rollback-" + uuid.uuid4().hex
    with pytest.raises(RuntimeError, match="force rollback"):
        with mysql_db.transaction() as connection:
            cursor = connection.cursor()
            cursor.execute("INSERT INTO knowledge_bases (id,knowledge_base_key,name) VALUES (%s,%s,%s)", (identity, key, "before"))
            cursor.close()
            raise RuntimeError("force rollback")
    assert sql(mysql_db, "SELECT id FROM knowledge_bases WHERE id=%s", (identity,)) == []
    with mysql_db.transaction() as connection:
        cursor = connection.cursor()
        cursor.execute("INSERT INTO knowledge_bases (id,knowledge_base_key,name) VALUES (%s,%s,%s)", (identity, key, "after"))
        cursor.close()
    assert sql(mysql_db, "SELECT name FROM knowledge_bases WHERE id=%s", (identity,))[0]["name"] == "after"


def test_registry_idempotence_and_parameterized_unicode_values(mysql_db):
    from tribal.storage import ensure_domain, ensure_knowledge_base, get_knowledge_base
    key = "registry-" + uuid.uuid4().hex
    name = "苗 '; DROP TABLE documents; --"
    first = ensure_knowledge_base(mysql_db, key=key, name=name)
    second = ensure_knowledge_base(mysql_db, key=key, name=name)
    assert first["knowledge_base"]["id"] == second["knowledge_base"]["id"]
    row = get_knowledge_base(mysql_db, knowledge_base=key)["knowledge_base"]
    assert row["name"] == name
    assert row["active_profile_id"] is None
    assert row["knowledge_generation"] == row["indexing_generation"] == 0
    domain = ensure_domain(mysql_db, knowledge_base=key, key="seed", name="Seed")
    assert ensure_domain(mysql_db, knowledge_base=key, key="seed", name="Seed")["domain"]["id"] == domain["domain"]["id"]
    assert domain["domain"]["knowledge_base_id"] == row["id"]
    assert uuid.UUID(row["id"]).version == 4


def test_domains_are_scoped_to_knowledge_base(mysql_db, registered_kb):
    from tribal.storage import ensure_domain, ensure_knowledge_base
    other = "other-" + uuid.uuid4().hex
    ensure_knowledge_base(mysql_db, key=other, name="Other")
    domain = ensure_domain(mysql_db, knowledge_base=other, key="research", name="Research")
    assert domain["domain"]["id"] != registered_kb["domain"]["id"]
    assert domain["domain"]["knowledge_base_id"] != registered_kb["id"]


def test_default_profile_is_immutable_and_json_equality_ignores_key_order(mysql_db):
    from tribal.errors import TribalError
    from tribal.storage import ensure_profile, get_profile
    result = ensure_profile(mysql_db)
    profile = result["profile"]
    expected = dict(wrapper="tribal-title-headings-v1", encoding="cl100k_base", max_input_tokens=8192,
                    distance="cosine", normalization="l2-float32-v1")
    assert profile["configuration"] == expected
    assert profile["dimensions"] == 1536
    assert profile["model_version"] is None
    assert get_profile(mysql_db, profile_id=profile["id"])["profile"] == profile
    assert ensure_profile(mysql_db, configuration=dict(reversed(list(expected.items()))))["profile"]["id"] == profile["id"]
    with pytest.raises(TribalError) as failure:
        ensure_profile(mysql_db, configuration={**expected, "max_input_tokens": 10})
    assert failure.value.code == "E_CONFLICT"


@pytest.mark.parametrize("kwargs", [{}, {"profile_id": "20000000-0000-4000-8000-000000000001", "key": "both"}])
def test_profile_lookup_requires_exactly_one_identity(mysql_db, kwargs):
    from tribal.errors import TribalError
    from tribal.storage import get_profile
    with pytest.raises(TribalError) as failure:
        get_profile(mysql_db, **kwargs)
    assert failure.value.code == "E_ARGUMENT"


def test_missing_registry_rows_have_explicit_not_found(mysql_db):
    from tribal.errors import TribalError
    from tribal.storage import get_knowledge_base, get_profile
    for operation in (lambda: get_knowledge_base(mysql_db, knowledge_base="missing-" + uuid.uuid4().hex),
                      lambda: get_profile(mysql_db, key="missing-" + uuid.uuid4().hex)):
        with pytest.raises(TribalError) as failure:
            operation()
        assert failure.value.code == "E_NOT_FOUND"


def test_generation_changes_are_atomic_with_transaction(mysql_db, registered_kb):
    from tribal.storage import advance_generations, get_knowledge_base, lock_knowledge_base
    key = registered_kb["key"]
    with pytest.raises(RuntimeError):
        with mysql_db.transaction() as connection:
            row = lock_knowledge_base(connection, key)
            advance_generations(connection, row["id"], knowledge=True, indexing=True)
            raise RuntimeError("rollback generations")
    assert get_knowledge_base(mysql_db, knowledge_base=key)["knowledge_base"]["knowledge_generation"] == 0
    with mysql_db.transaction() as connection:
        row = lock_knowledge_base(connection, key)
        advance_generations(connection, row["id"], knowledge=True, indexing=True)
    row = get_knowledge_base(mysql_db, knowledge_base=key)["knowledge_base"]
    assert row["knowledge_generation"] == row["indexing_generation"] == 1


def test_knowledge_base_lock_serializes_separate_connections(mysql_db, registered_kb):
    from tribal.storage import lock_knowledge_base
    entered, acquired = threading.Event(), threading.Event()
    def contender():
        with mysql_db.transaction() as connection:
            entered.set()
            lock_knowledge_base(connection, registered_kb["key"])
            acquired.set()
    with ThreadPoolExecutor(max_workers=1) as executor:
        with mysql_db.transaction() as connection:
            lock_knowledge_base(connection, registered_kb["key"])
            future = executor.submit(contender)
            assert entered.wait(5)
            assert not acquired.wait(0.2), "another transaction acquired the held KB lock"
        future.result(timeout=10)
    assert acquired.is_set()


def test_readonly_transaction_keeps_one_committed_snapshot(mysql_db, registered_kb):
    with mysql_db.transaction(readonly=True) as connection:
        cursor = connection.cursor(dictionary=True)
        cursor.execute("SELECT name FROM knowledge_bases WHERE id=%s", (uuid.UUID(registered_kb["id"]).bytes,))
        before = cursor.fetchone()["name"]
        with ThreadPoolExecutor(max_workers=1) as executor:
            executor.submit(sql, mysql_db, "UPDATE knowledge_bases SET name=%s WHERE id=%s", ("changed concurrently", uuid.UUID(registered_kb["id"]).bytes)).result(timeout=10)
        cursor.execute("SELECT name FROM knowledge_bases WHERE id=%s", (uuid.UUID(registered_kb["id"]).bytes,))
        assert cursor.fetchone()["name"] == before
        cursor.close()
    assert sql(mysql_db, "SELECT name FROM knowledge_bases WHERE id=%s", (uuid.UUID(registered_kb["id"]).bytes,))[0]["name"] == "changed concurrently"


def test_server_vector_functions_preserve_ieee_float32(mysql_db):
    values = [0.1, -0.2, 0.3]
    row = sql(mysql_db, "SELECT CAST(STRING_TO_VECTOR(%s) AS BINARY) AS value", (json.dumps(values),))[0]
    assert bytes(row["value"]) == struct.pack("<fff", *values)


@pytest.mark.parametrize("dimensions", [True, False, 0, -1, 16384, 3.5, "3"])
def test_profile_dimensions_require_positive_nonboolean_integer(mysql_db, dimensions):
    from tribal.errors import TribalError
    from tribal.storage import ensure_profile
    configuration = dict(wrapper="tribal-title-headings-v1", encoding="cl100k_base", max_input_tokens=8192,
                         distance="cosine", normalization="l2-float32-v1")
    with pytest.raises(TribalError) as failure:
        ensure_profile(mysql_db, key="bad-dim-" + uuid.uuid4().hex, dimensions=dimensions, configuration=configuration)
    assert failure.value.code == "E_ARGUMENT"


@pytest.mark.parametrize("changes", [
    {"wrapper": "unsupported"}, {"distance": "dot_product"}, {"normalization": "none"},
    {"encoding": "not-a-registered-encoding"}, {"max_input_tokens": 0},
    {"max_input_tokens": -1}, {"max_input_tokens": True}, {"max_input_tokens": 1.5},
    {"max_input_tokens": 8193}, {"additional": float("nan")}, {"additional": float("inf")},
])
def test_profile_rejects_unsupported_or_nonfinite_configuration(mysql_db, changes):
    from tribal.errors import TribalError
    from tribal.storage import ensure_profile
    configuration = dict(wrapper="tribal-title-headings-v1", encoding="cl100k_base", max_input_tokens=8192,
                         distance="cosine", normalization="l2-float32-v1")
    with pytest.raises(TribalError) as failure:
        ensure_profile(mysql_db, key="bad-config-" + uuid.uuid4().hex, configuration={**configuration, **changes})
    assert failure.value.code == "E_ARGUMENT"
    json.dumps(failure.value.as_dict(), allow_nan=False)


@pytest.mark.parametrize("missing", ["wrapper", "encoding", "max_input_tokens", "distance", "normalization"])
def test_profile_requires_complete_explicit_configuration(mysql_db, missing):
    from tribal.errors import TribalError
    from tribal.storage import ensure_profile
    configuration = dict(wrapper="tribal-title-headings-v1", encoding="cl100k_base", max_input_tokens=8192,
                         distance="cosine", normalization="l2-float32-v1")
    del configuration[missing]
    with pytest.raises(TribalError) as failure:
        ensure_profile(mysql_db, key="missing-config-" + uuid.uuid4().hex, configuration=configuration)
    assert failure.value.code == "E_ARGUMENT"


def test_custom_model_positive_limit_and_extra_finite_json_are_immutable(mysql_db):
    from tribal.errors import TribalError
    from tribal.storage import ensure_profile
    key = "custom-profile-" + uuid.uuid4().hex
    config = dict(wrapper="tribal-title-headings-v1", encoding="cl100k_base", max_input_tokens=20000,
                  distance="cosine", normalization="l2-float32-v1", additional={"revision": [1, 2.5, "界"]})
    result = ensure_profile(mysql_db, key=key, provider="test", model="explicit-test-model", dimensions=3, configuration=config)
    assert result["profile"]["configuration"] == config
    with pytest.raises(TribalError) as failure:
        ensure_profile(mysql_db, key=key, provider="test", model="explicit-test-model", dimensions=3,
                       configuration={**config, "additional": {"revision": [2]}})
    assert failure.value.code == "E_CONFLICT"
