"""Construct the Tribal management and project worker ASGI applications."""

from __future__ import annotations

import os
import sqlite3
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException

from tribal.authentication import add_management_session_middleware, build_management_auth_routes
from tribal.kubernetes_provisioner import KubernetesProvisioner
from tribal.project_management import build_project_management_routes
from tribal.project_store import ProjectStore
from tribal.project_worker import build_project_worker
from tribal.settings import Settings, SettingsError


def build_management_app(
    settings: Settings | None = None,
    store: ProjectStore | None = None,
    provisioner: Any | None = None,
    *,
    database_path: str | Path | None = None,
    worker_image: str | None = None,
    template_root: str | Path | None = None,
) -> FastAPI:
    """Build the authenticated project manager.

    The optional components support local assembly and isolated callers. Production
    construction reads the fixed runtime environment and creates the real SQLite and
    Kubernetes adapters. Missing configuration raises instead of starting a fake app.
    """
    config = settings or Settings.from_env()
    if not config.session_signing_key:
        raise SettingsError("SESSION_SIGNING_KEY must be set for management browser sessions")

    if store is None:
        db_path = database_path or os.environ.get("DATABASE_PATH", "").strip()
        if not db_path:
            raise SettingsError("DATABASE_PATH must be set for management mode")
        store = ProjectStore(db_path)

    if provisioner is None:
        image = worker_image or os.environ.get("WORKER_IMAGE", "").strip()
        if not image:
            raise SettingsError("WORKER_IMAGE must be set for management mode")
        templates = template_root or os.environ.get("K8S_TEMPLATE_ROOT", "").strip()
        if not templates:
            raise SettingsError("K8S_TEMPLATE_ROOT must be set for management mode")
        if not Path(templates).is_dir():
            raise SettingsError("K8S_TEMPLATE_ROOT must point to a directory")
        provisioner = KubernetesProvisioner.from_cluster(
            public_base_url=config.public_base_url,
            worker_image=image,
            template_root=templates,
        )

    app = FastAPI(title="Tribal project manager", docs_url=None, redoc_url=None)
    add_management_session_middleware(app, config)
    app.include_router(build_management_auth_routes(config))
    app.include_router(build_project_management_routes(store, provisioner, config.public_base_url))

    @app.get("/healthz", include_in_schema=False)
    async def healthz() -> dict[str, str]:
        try:
            with sqlite3.connect(store.database_path, timeout=2) as connection:
                connection.execute("SELECT 1").fetchone()
        except (sqlite3.Error, OSError) as exc:
            raise HTTPException(status_code=503, detail="Project database is unavailable") from exc
        return {"status": "ok"}

    @app.get("/readyz", include_in_schema=False)
    async def readyz() -> dict[str, str]:
        return await healthz()

    return app


def build_worker_app(settings: Settings | None = None) -> Any:
    """Build the stateless project MCP worker from the worker environment."""
    return build_project_worker(settings or Settings.from_env())
