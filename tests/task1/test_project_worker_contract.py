from dataclasses import replace
from uuid import UUID

import pytest

from tribal.project_worker import create_project_context
from tribal.settings import Settings, SettingsError


PROJECT_ID = "45c62769-57ed-479d-9b95-fbb75e0dba95"


def worker_settings(project_id: str, project_name: str) -> Settings:
    return Settings(
        public_base_url="https://tribal.example",
        github_client_id="github-client",
        github_client_secret="github-secret",
        token_signing_key="worker-token-key-with-sufficient-entropy",
        session_signing_key="management-session-key-with-sufficient-entropy",
        project_id=project_id,
        project_name=project_name,
        allowed_github_ids=frozenset({101}),
    )


def test_worker_context_is_bound_to_its_project_configuration():
    first_id = PROJECT_ID
    second_id = str(UUID("fc0b6d32-9ed4-4e4a-b54a-7ad2c60451fe"))

    first = create_project_context(worker_settings(first_id, "Alpha"))
    second = create_project_context(worker_settings(second_id, "Beta"))

    assert first == {
        "id": first_id,
        "name": "Alpha",
        "sample": True,
        "context": "Sample context for Alpha.",
    }
    assert second["id"] == second_id
    assert second["name"] == "Beta"
    assert first["id"] != second["id"]
    assert first["context"] != second["context"]


def test_worker_context_refuses_missing_allowlist():
    settings = worker_settings(PROJECT_ID, "Alpha")
    settings = replace(settings, allowed_github_ids=frozenset())

    with pytest.raises(SettingsError, match="ALLOWED_GITHUB_IDS"):
        create_project_context(settings)
