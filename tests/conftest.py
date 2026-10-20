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
