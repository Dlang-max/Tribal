"""Environment-backed settings shared by the management app and project workers."""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Mapping
from urllib.parse import urlsplit, urlunsplit


class SettingsError(ValueError):
    """Raised when required application configuration is absent or invalid."""


def _required(env: Mapping[str, str], name: str) -> str:
    value = env.get(name, "").strip()
    if not value:
        raise SettingsError(f"{name} must be set")
    return value


def _public_root(value: str) -> str:
    parsed = urlsplit(value)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise SettingsError("PUBLIC_BASE_URL must be an absolute http(s) URL")
    if parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise SettingsError("PUBLIC_BASE_URL must not include credentials, query, or fragment")
    if parsed.path not in {"", "/"}:
        raise SettingsError("PUBLIC_BASE_URL must be an origin root; path prefixes are unsupported")
    return urlunsplit((parsed.scheme, parsed.netloc, "", "", ""))


@dataclass(frozen=True, slots=True)
class Settings:
    """Configuration used by worker and management authentication flows."""

    public_base_url: str
    github_client_id: str
    github_client_secret: str
    token_signing_key: str
    session_signing_key: str | None = None
    project_id: str | None = None
    project_name: str | None = None
    allowed_github_ids: frozenset[int] = frozenset()

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> Settings:
        """Load and validate the documented environment contract."""
        source = os.environ if env is None else env
        allowed_raw = source.get("ALLOWED_GITHUB_IDS", "")
        allowed: set[int] = set()
        for candidate in allowed_raw.split(","):
            candidate = candidate.strip()
            if not candidate:
                continue
            try:
                github_id = int(candidate)
            except ValueError as exc:
                raise SettingsError("ALLOWED_GITHUB_IDS must contain comma-separated numeric IDs") from exc
            if github_id <= 0:
                raise SettingsError("ALLOWED_GITHUB_IDS values must be positive numeric IDs")
            allowed.add(github_id)

        project_id = source.get("PROJECT_ID", "").strip() or None
        project_name = source.get("PROJECT_NAME", "").strip() or None
        if project_id is not None and project_name is None:
            raise SettingsError("PROJECT_NAME must be set when PROJECT_ID is set")
        if project_name is not None and project_id is None:
            raise SettingsError("PROJECT_ID must be set when PROJECT_NAME is set")

        return cls(
            public_base_url=_public_root(_required(source, "PUBLIC_BASE_URL")),
            github_client_id=_required(source, "GITHUB_CLIENT_ID"),
            github_client_secret=_required(source, "GITHUB_CLIENT_SECRET"),
            token_signing_key=_required(source, "TOKEN_SIGNING_KEY"),
            session_signing_key=source.get("SESSION_SIGNING_KEY", "").strip() or None,
            project_id=project_id,
            project_name=project_name,
            allowed_github_ids=frozenset(allowed),
        )

    def require_worker_config(self) -> None:
        if not self.project_id or not self.project_name:
            raise SettingsError("PROJECT_ID and PROJECT_NAME are required in worker mode")
        if not self.allowed_github_ids:
            raise SettingsError("ALLOWED_GITHUB_IDS must contain at least one GitHub account ID")


def get_settings() -> Settings:
    """Load process settings."""
    return Settings.from_env()
