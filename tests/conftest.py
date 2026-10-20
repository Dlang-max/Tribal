"""Explicit prerequisites for independent database and live-provider checks."""
from __future__ import annotations

import json
import os

import pytest


def pytest_configure(config):
    config.addinivalue_line("markers", "mysql: requires an explicitly configured real MySQL 9.7 server")
    config.addinivalue_line("markers", "live_openai: requires explicit opt-in and real provider credentials")
    config.addinivalue_line("markers", "benchmark: separately runnable exact-search measurement")


@pytest.fixture(scope="session")
def mysql_config():
    raw = os.environ.get("TRIBAL_TEST_MYSQL_CONFIG")
    if raw is None:
        pytest.skip("real MySQL prerequisite unavailable: set TRIBAL_TEST_MYSQL_CONFIG to connector JSON")
    try:
        config = json.loads(raw)
    except json.JSONDecodeError:
        pytest.fail("TRIBAL_TEST_MYSQL_CONFIG must be a JSON object", pytrace=False)
    if not isinstance(config, dict) or not config.get("database"):
        pytest.fail("TRIBAL_TEST_MYSQL_CONFIG must include an isolated test database", pytrace=False)
    return config


@pytest.fixture(scope="session")
def live_openai_enabled():
    if os.environ.get("TRIBAL_TEST_LIVE_OPENAI") != "1":
        pytest.skip("live OpenAI smoke is opt-in: set TRIBAL_TEST_LIVE_OPENAI=1")
    if not os.environ.get("OPENAI_API_KEY"):
        pytest.fail("live smoke requested but OPENAI_API_KEY is absent", pytrace=False)


@pytest.fixture(scope="session")
def mysql_db(mysql_config):
    # A missing implementation is a failure once the explicit service prerequisite
    # is supplied; it is never converted to a prerequisite skip.
    from tribal.storage import Database, migrate
    db = Database(**mysql_config)
    migrate(db)
    yield db
    db.close()


@pytest.fixture
def registered_kb(mysql_db):
    from uuid import uuid4
    from tribal.storage import ensure_domain, ensure_knowledge_base
    key = "test-" + uuid4().hex
    kb = ensure_knowledge_base(mysql_db, key=key, name="Independent acceptance")
    domain = ensure_domain(mysql_db, knowledge_base=key, key="research", name="Research")
    return dict(key=key, id=kb["knowledge_base"]["id"], domain=domain["domain"])


@pytest.fixture
def active_kb(mysql_db, registered_kb):
    from tribal.embeddings import activate_profile
    from tribal.storage import ensure_profile
    configuration = dict(wrapper="tribal-title-headings-v1", encoding="cl100k_base",
                         max_input_tokens=8192, distance="cosine", normalization="l2-float32-v1")
    profile = ensure_profile(mysql_db, key="independent-test-3-v1", dimensions=3,
                             configuration=configuration)["profile"]
    activate_profile(mysql_db, knowledge_base=registered_kb["key"], profile_id=profile["id"])
    return {**registered_kb, "profile": profile}


@pytest.fixture
def make_note(active_kb):
    from uuid import uuid4
    from acceptance_helpers import note
    def factory(body="A useful observation.\n", **changes):
        metadata = {"knowledge_base": active_kb["key"], "id": str(uuid4()), **changes}
        return note(body, **metadata)
    return factory
