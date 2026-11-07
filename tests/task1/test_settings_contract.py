import pytest

from tribal.settings import Settings, SettingsError


@pytest.fixture
def valid_environment():
    return {
        "PUBLIC_BASE_URL": "https://tribal.example/",
        "GITHUB_CLIENT_ID": "github-client",
        "GITHUB_CLIENT_SECRET": "github-secret",
        "TOKEN_SIGNING_KEY": "worker-token-key-with-sufficient-entropy",
        "SESSION_SIGNING_KEY": "management-session-key-with-sufficient-entropy",
    }


def test_settings_normalize_public_root_and_parse_numeric_allowlist(valid_environment):
    valid_environment.update(
        PUBLIC_BASE_URL="https://tribal.example/",
        PROJECT_ID="45c62769-57ed-479d-9b95-fbb75e0dba95",
        PROJECT_NAME="Example",
        ALLOWED_GITHUB_IDS=" 42, 17,42 ",
    )

    settings = Settings.from_env(valid_environment)

    assert settings.public_base_url == "https://tribal.example"
    assert settings.allowed_github_ids == frozenset({17, 42})
    settings.require_worker_config()


@pytest.mark.parametrize("value", ["", "0", "-1", "not-a-github-id"])
def test_settings_reject_invalid_allowlist_ids(valid_environment, value):
    valid_environment["ALLOWED_GITHUB_IDS"] = value

    if value == "":
        # An empty allowlist is valid for management settings, but cannot run a worker.
        valid_environment["PROJECT_ID"] = "45c62769-57ed-479d-9b95-fbb75e0dba95"
        valid_environment["PROJECT_NAME"] = "Example"
        settings = Settings.from_env(valid_environment)
        with pytest.raises(SettingsError, match="ALLOWED_GITHUB_IDS"):
            settings.require_worker_config()
    else:
        with pytest.raises(SettingsError, match="ALLOWED_GITHUB_IDS"):
            Settings.from_env(valid_environment)


def test_settings_reject_partial_project_configuration(valid_environment):
    valid_environment["PROJECT_ID"] = "45c62769-57ed-479d-9b95-fbb75e0dba95"

    with pytest.raises(SettingsError, match="PROJECT_NAME"):
        Settings.from_env(valid_environment)


def test_worker_configuration_does_not_require_management_session_key(valid_environment):
    valid_environment.update(
        PROJECT_ID="45c62769-57ed-479d-9b95-fbb75e0dba95",
        PROJECT_NAME="Example",
        ALLOWED_GITHUB_IDS="42",
    )
    valid_environment.pop("SESSION_SIGNING_KEY")

    settings = Settings.from_env(valid_environment)

    assert settings.session_signing_key is None
    settings.require_worker_config()


def test_settings_reject_public_urls_that_cannot_be_used_as_origins(valid_environment):
    for url in (
        "//tribal.example",
        "file:///tmp/tribal",
        "https://user:password@tribal.example",
        "https://tribal.example?next=/",
        "https://tribal.example/#fragment",
        "https://tribal.example/base",
    ):
        valid_environment["PUBLIC_BASE_URL"] = url
        with pytest.raises(SettingsError, match="PUBLIC_BASE_URL"):
            Settings.from_env(valid_environment)
