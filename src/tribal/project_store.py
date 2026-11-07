"""Small SQLite store for project ownership, membership, and provisioning state."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Literal
from uuid import uuid4

ProjectStatus = Literal["provisioning", "ready", "failed"]


@dataclass(frozen=True, slots=True)
class Project:
    id: str
    name: str
    owner_github_id: int
    owner_login: str
    mcp_url: str
    status: ProjectStatus
    error: str | None
    token_signing_key: str


class ProjectStore:
    """Persist project records and their initial creator-only allowlist."""

    def __init__(self, database_path: str | Path) -> None:
        self.database_path = str(database_path)
        if self.database_path != ":memory:":
            Path(self.database_path).expanduser().parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database_path, timeout=10)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA busy_timeout = 10000")
        return connection

    def _initialize(self) -> None:
        with self._connect() as connection:
            connection.execute("PRAGMA journal_mode = WAL")
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS projects (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    owner_github_id INTEGER NOT NULL,
                    owner_login TEXT NOT NULL,
                    mcp_url TEXT NOT NULL,
                    status TEXT NOT NULL CHECK(status IN ('provisioning', 'ready', 'failed')),
                    error TEXT,
                    token_signing_key TEXT NOT NULL,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );
                CREATE INDEX IF NOT EXISTS projects_owner_idx
                    ON projects(owner_github_id, created_at);
                CREATE TABLE IF NOT EXISTS project_members (
                    project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
                    github_id INTEGER NOT NULL,
                    PRIMARY KEY(project_id, github_id)
                );
                """
            )

    @staticmethod
    def _project(row: sqlite3.Row) -> Project:
        return Project(
            id=row["id"],
            name=row["name"],
            owner_github_id=row["owner_github_id"],
            owner_login=row["owner_login"],
            mcp_url=row["mcp_url"],
            status=row["status"],
            error=row["error"],
            token_signing_key=row["token_signing_key"],
        )

    def create_project(
        self,
        name: str,
        owner_id: int,
        owner_login: str,
        mcp_url: str,
        token_signing_key: str,
        project_id: str | None = None,
    ) -> Project:
        project_id = project_id or str(uuid4())
        with self._connect() as connection:
            connection.execute(
                """INSERT INTO projects
                   (id, name, owner_github_id, owner_login, mcp_url, status, token_signing_key)
                   VALUES (?, ?, ?, ?, ?, 'provisioning', ?)""",
                (project_id, name, owner_id, owner_login, mcp_url, token_signing_key),
            )
            connection.execute(
                "INSERT INTO project_members(project_id, github_id) VALUES (?, ?)",
                (project_id, owner_id),
            )
            row = connection.execute("SELECT * FROM projects WHERE id = ?", (project_id,)).fetchone()
        return self._project(row)

    def list_projects(self, owner_id: int) -> list[Project]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT * FROM projects WHERE owner_github_id = ? ORDER BY created_at DESC, id",
                (owner_id,),
            ).fetchall()
        return [self._project(row) for row in rows]

    def get_project_for_owner(self, project_id: str, owner_id: int) -> Project | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM projects WHERE id = ? AND owner_github_id = ?",
                (project_id, owner_id),
            ).fetchone()
        return self._project(row) if row else None

    def list_incomplete_projects(self) -> list[Project]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT * FROM projects WHERE status IN ('provisioning', 'failed') ORDER BY created_at"
            ).fetchall()
        return [self._project(row) for row in rows]

    def set_status(self, project_id: str, status: ProjectStatus, error: str | None = None) -> None:
        if status not in {"provisioning", "ready", "failed"}:
            raise ValueError("Unsupported project status")
        with self._connect() as connection:
            connection.execute(
                "UPDATE projects SET status = ?, error = ? WHERE id = ?",
                (status, error[:2000] if error else None, project_id),
            )

    def allowed_github_ids(self, project_id: str) -> frozenset[int]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT github_id FROM project_members WHERE project_id = ? ORDER BY github_id",
                (project_id,),
            ).fetchall()
        return frozenset(row["github_id"] for row in rows)
