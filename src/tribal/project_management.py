"""Authenticated project management page, API, and provisioning orchestration."""

from __future__ import annotations

import asyncio
import html
import secrets
from pathlib import Path
from typing import Any
from uuid import uuid4

from fastapi import APIRouter, Header, HTTPException, Request, status
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, ConfigDict, Field

from tribal.authentication import csrf_token_for, get_current_user, verify_csrf_token
from tribal.project_store import Project, ProjectStore


class CreateProjectRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=100)


def build_project_management_routes(
    store: ProjectStore,
    provisioner: Any,
    public_base_url: str,
    *,
    reconcile_on_startup: bool = True,
) -> APIRouter:
    """Build page and project APIs; mount with Task 1 auth routes and session middleware.

    ``provisioner`` is intentionally duck typed and must implement synchronous
    ``provision(project_id, name, allowed_github_ids, token_signing_key)`` and
    ``is_ready(project_id)`` methods. Blocking Kubernetes calls run in worker threads.
    """
    router = APIRouter()
    base_url = public_base_url.rstrip("/")
    template_path = Path(__file__).parent / "templates" / "projects.html"
    pending: dict[str, asyncio.Task[None]] = {}

    async def run_provisioning(project: Project) -> None:
        try:
            store.set_status(project.id, "provisioning")
            allowed_ids = store.allowed_github_ids(project.id)
            if not allowed_ids:
                raise RuntimeError("Project has no authorized GitHub members")
            await asyncio.to_thread(
                provisioner.provision,
                project.id,
                project.name,
                allowed_ids,
                project.token_signing_key,
            )
            ready = await asyncio.to_thread(provisioner.is_ready, project.id)
            if not ready:
                raise RuntimeError("Worker deployment did not report available replicas")
            store.set_status(project.id, "ready")
        except Exception as exc:
            # Persist a concise message for the owner. Never log or return signing material.
            message = str(exc).strip() or exc.__class__.__name__
            message = message.replace(project.token_signing_key, "[redacted]")
            store.set_status(project.id, "failed", message)
        finally:
            pending.pop(project.id, None)

    def schedule(project: Project) -> None:
        task = pending.get(project.id)
        if task is None or task.done():
            pending[project.id] = asyncio.create_task(run_provisioning(project))

    async def reconcile() -> None:
        for project in store.list_incomplete_projects():
            schedule(project)

    if reconcile_on_startup:

        @router.on_event("startup")
        async def reconcile_projects_on_startup() -> None:
            await reconcile()

    @router.get("/", response_class=HTMLResponse, include_in_schema=False)
    async def projects_page(request: Request) -> HTMLResponse:
        identity = get_current_user(request)
        csrf = csrf_token_for(request) if identity else ""
        html_page = template_path.read_text(encoding="utf-8")
        page = html_page.replace("{{csrf_token}}", html.escape(csrf, quote=True))
        page = page.replace("{{github_login}}", html.escape(identity.login, quote=True) if identity else "")
        page = page.replace("{{signed_in}}", "true" if identity else "false")
        return HTMLResponse(page)

    @router.get("/api/projects")
    async def list_projects(request: Request) -> dict[str, Any]:
        identity = get_current_user(request)
        if identity is None:
            raise HTTPException(status_code=401, detail="Sign in with GitHub to continue")
        projects = store.list_projects(identity.github_id)
        for project in projects:
            await refresh_ready_state(project)
        return {"projects": [_project_payload(project) for project in store.list_projects(identity.github_id)]}

    @router.post("/api/projects", status_code=status.HTTP_202_ACCEPTED)
    async def create_project(
        payload: CreateProjectRequest,
        request: Request,
        csrf_token: str | None = Header(default=None, alias="X-CSRF-Token"),
    ) -> dict[str, str]:
        identity = get_current_user(request)
        if identity is None:
            raise HTTPException(status_code=401, detail="Sign in with GitHub to continue")
        if not verify_csrf_token(request, csrf_token):
            raise HTTPException(status_code=403, detail="Invalid CSRF token")
        name = payload.name.strip()
        if not name:
            raise HTTPException(status_code=422, detail="Project name cannot be blank")
        if len(name) > 100:
            raise HTTPException(status_code=422, detail="Project name must be 100 characters or fewer")
        project_id = str(uuid4())
        project = store.create_project(
            name=name,
            owner_id=identity.github_id,
            owner_login=identity.login,
            mcp_url=f"{base_url}/projects/{project_id}/mcp",
            token_signing_key=secrets.token_urlsafe(48),
            project_id=project_id,
        )
        schedule(project)
        return {
            "id": project.id,
            "status": project.status,
            "status_url": f"/api/projects/{project.id}",
        }

    @router.get("/api/projects/{project_id}")
    async def get_project(project_id: str, request: Request) -> dict[str, Any]:
        identity = get_current_user(request)
        if identity is None:
            raise HTTPException(status_code=401, detail="Sign in with GitHub to continue")
        project = store.get_project_for_owner(project_id, identity.github_id)
        if project is None:
            raise HTTPException(status_code=404, detail="Project not found")
        project = await refresh_ready_state(project)
        return _project_payload(project)

    async def refresh_ready_state(project: Project) -> Project:
        if project.status != "ready":
            return project
        try:
            live_ready = await asyncio.to_thread(provisioner.is_ready, project.id)
        except Exception as exc:
            live_ready = False
            message = f"Worker readiness check failed: {str(exc).strip() or exc.__class__.__name__}"
            message = message.replace(project.token_signing_key, "[redacted]")
        else:
            message = "Worker deployment is not currently ready."
        if live_ready:
            return project
        store.set_status(project.id, "provisioning", message)
        updated = store.get_project_for_owner(project.id, project.owner_github_id)
        if updated is None:
            return project
        schedule(updated)
        return updated

    def _project_payload(project: Project) -> dict[str, Any]:
        return {
            "id": project.id,
            "name": project.name,
            "mcp_url": project.mcp_url,
            "status": project.status,
            "error": project.error,
            "status_url": f"/api/projects/{project.id}",
        }

    return router
