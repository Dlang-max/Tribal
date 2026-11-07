import threading
import time

from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

from tribal.authentication import add_management_session_middleware
from tribal.project_management import build_project_management_routes
from tribal.project_store import ProjectStore
from tribal.settings import Settings


SESSION_KEY = "a-test-session-signing-key-with-enough-length"
PUBLIC_BASE_URL = "https://tribal.example"
CSRF_TOKEN = "test-csrf-token-with-more-than-32-characters"


class FakeProvisioner:
    def __init__(self, *, failure=None, initially_ready=True):
        self.failure = failure
        self.initially_ready = initially_ready
        self.calls = []
        self.ready = {}
        self.started = threading.Event()
        self.second_call_started = threading.Event()
        self.hold_second_call = False
        self.release_second_call = threading.Event()
        self.lock = threading.Lock()

    def provision(self, project_id, name, allowed_github_ids, token_signing_key):
        with self.lock:
            self.calls.append((project_id, name, allowed_github_ids, token_signing_key))
            call_number = sum(call[0] == project_id for call in self.calls)
        self.started.set()
        if self.hold_second_call and call_number == 2:
            self.second_call_started.set()
            self.release_second_call.wait(timeout=2)
        if self.failure is not None:
            raise RuntimeError(self.failure(token_signing_key) if callable(self.failure) else self.failure)
        with self.lock:
            self.ready[project_id] = self.initially_ready

    def is_ready(self, project_id):
        with self.lock:
            return self.ready.get(project_id, False)

    def set_ready(self, project_id, ready):
        with self.lock:
            self.ready[project_id] = ready


def make_app(database_path, provisioner, *, reconcile_on_startup=False):
    store = ProjectStore(database_path)
    app = FastAPI()
    settings = Settings(
        public_base_url=PUBLIC_BASE_URL,
        github_client_id="client-id",
        github_client_secret="client-secret",
        token_signing_key="worker-signing-key",
        session_signing_key=SESSION_KEY,
    )
    add_management_session_middleware(app, settings)
    app.include_router(
        build_project_management_routes(
            store,
            provisioner,
            PUBLIC_BASE_URL,
            reconcile_on_startup=reconcile_on_startup,
        )
    )

    @app.get("/__test/login/{github_id}/{login}")
    async def test_login(request: Request, github_id: int, login: str):
        request.session["github_identity"] = {
            "github_id": github_id,
            "login": login,
            "name": None,
            "email": None,
        }
        request.session["csrf_token"] = CSRF_TOKEN
        return {"ok": True}

    return app, store


def sign_in(client, github_id=41, login="alice"):
    response = client.get(f"/__test/login/{github_id}/{login}")
    assert response.status_code == 200


def wait_for_project_status(client, status_url, expected, timeout=2):
    deadline = time.monotonic() + timeout
    last_payload = None
    while time.monotonic() < deadline:
        response = client.get(status_url)
        assert response.status_code == 200
        last_payload = response.json()
        if last_payload["status"] == expected:
            return last_payload
        time.sleep(0.01)
    raise AssertionError(f"Project did not reach {expected!r}; last status: {last_payload}")


def test_management_api_requires_login_csrf_and_valid_project_names(tmp_path):
    provisioner = FakeProvisioner()
    app, store = make_app(tmp_path / "projects.sqlite3", provisioner)

    with TestClient(app, base_url=PUBLIC_BASE_URL) as client:
        assert client.get("/api/projects").status_code == 401
        assert client.post("/api/projects", json={"name": "Unauthorized"}).status_code == 401
        sign_in(client)
        assert client.post("/api/projects", json={"name": "No CSRF"}).status_code == 403
        invalid_extra = client.post(
            "/api/projects",
            json={"name": "Bad input", "owner_id": 9},
            headers={"X-CSRF-Token": CSRF_TOKEN},
        )
        blank_name = client.post(
            "/api/projects",
            json={"name": "   "},
            headers={"X-CSRF-Token": CSRF_TOKEN},
        )

    assert invalid_extra.status_code == 422
    assert blank_name.status_code == 422
    assert store.list_projects(41) == []
    assert provisioner.calls == []


def test_project_creation_status_and_urls_are_visible_only_to_owner(tmp_path):
    provisioner = FakeProvisioner()
    app, store = make_app(tmp_path / "projects.sqlite3", provisioner)

    with TestClient(app, base_url=PUBLIC_BASE_URL) as owner:
        sign_in(owner, 41, "alice")
        created = owner.post(
            "/api/projects",
            json={"name": "Compiler notes"},
            headers={"X-CSRF-Token": CSRF_TOKEN},
        )
        assert created.status_code == 202
        response = created.json()
        assert response["status"] == "provisioning"
        assert response["status_url"] == f"/api/projects/{response['id']}"
        ready = wait_for_project_status(owner, response["status_url"], "ready")
        listed = owner.get("/api/projects").json()["projects"]

    with TestClient(app, base_url=PUBLIC_BASE_URL) as another_user:
        sign_in(another_user, 99, "mallory")
        hidden = another_user.get(response["status_url"])
        other_list = another_user.get("/api/projects").json()["projects"]

    assert ready["name"] == "Compiler notes"
    assert ready["mcp_url"] == f"{PUBLIC_BASE_URL}/projects/{response['id']}/mcp"
    assert ready["error"] is None
    assert "token_signing_key" not in ready
    assert len(listed) == 1 and listed[0]["id"] == response["id"]
    assert hidden.status_code == 404
    assert other_list == []
    project = store.get_project_for_owner(response["id"], 41)
    assert project is not None and project.status == "ready"
    assert store.allowed_github_ids(response["id"]) == frozenset({41})
    assert provisioner.calls[0][2] == frozenset({41})


def test_provisioning_failure_is_visible_and_signing_key_is_redacted(tmp_path):
    provisioner = FakeProvisioner(
        failure=lambda key: f"Kubernetes refused signing key {key}"
    )
    app, store = make_app(tmp_path / "projects.sqlite3", provisioner)

    with TestClient(app, base_url=PUBLIC_BASE_URL) as client:
        sign_in(client)
        created = client.post(
            "/api/projects",
            json={"name": "Fail visibly"},
            headers={"X-CSRF-Token": CSRF_TOKEN},
        ).json()
        failed = wait_for_project_status(client, created["status_url"], "failed")

    secret = provisioner.calls[0][3]
    assert failed["error"] == "Kubernetes refused signing key [redacted]"
    assert secret not in str(failed)
    persisted = store.get_project_for_owner(created["id"], 41)
    assert persisted is not None and persisted.status == "failed"
    assert persisted.error == failed["error"]


def test_project_is_failed_when_provision_returns_without_ready_replicas(tmp_path):
    provisioner = FakeProvisioner(initially_ready=False)
    app, store = make_app(tmp_path / "projects.sqlite3", provisioner)

    with TestClient(app, base_url=PUBLIC_BASE_URL) as client:
        sign_in(client)
        created = client.post(
            "/api/projects",
            json={"name": "No ready worker"},
            headers={"X-CSRF-Token": CSRF_TOKEN},
        ).json()
        failed = wait_for_project_status(client, created["status_url"], "failed")

    assert failed["error"] == "Worker deployment did not report available replicas"
    persisted = store.get_project_for_owner(created["id"], 41)
    assert persisted is not None
    assert persisted.status == "failed"
    assert persisted.status != "ready"


def test_ready_project_is_downgraded_when_live_worker_loses_readiness(tmp_path):
    provisioner = FakeProvisioner()
    provisioner.hold_second_call = True
    app, store = make_app(tmp_path / "projects.sqlite3", provisioner)

    with TestClient(app, base_url=PUBLIC_BASE_URL) as client:
        sign_in(client)
        created = client.post(
            "/api/projects",
            json={"name": "Readiness"},
            headers={"X-CSRF-Token": CSRF_TOKEN},
        ).json()
        ready = wait_for_project_status(client, created["status_url"], "ready")
        provisioner.set_ready(created["id"], False)
        downgraded = client.get(created["status_url"]).json()
        assert provisioner.second_call_started.wait(timeout=2)
        provisioner.release_second_call.set()

    assert ready["status"] == "ready"
    assert downgraded["status"] == "provisioning"
    assert downgraded["error"] == "Worker deployment is not currently ready."
    assert store.get_project_for_owner(created["id"], 41).status in {"ready", "provisioning"}


def test_startup_reconciles_persisted_provisioning_and_failed_projects(tmp_path):
    database = tmp_path / "projects.sqlite3"
    seed_store = ProjectStore(database)
    provisioning = seed_store.create_project(
        "Interrupted", 41, "alice", f"{PUBLIC_BASE_URL}/projects/a/mcp", "key-a"
    )
    failed = seed_store.create_project(
        "Previously failed", 42, "bob", f"{PUBLIC_BASE_URL}/projects/b/mcp", "key-b"
    )
    seed_store.set_status(failed.id, "failed", "Temporary outage")
    provisioner = FakeProvisioner()
    provisioner.started.clear()
    app, restarted_store = make_app(database, provisioner, reconcile_on_startup=True)

    with TestClient(app, base_url=PUBLIC_BASE_URL):
        deadline = time.monotonic() + 2
        while time.monotonic() < deadline:
            persisted = [
                restarted_store.get_project_for_owner(provisioning.id, 41),
                restarted_store.get_project_for_owner(failed.id, 42),
            ]
            if all(project.status == "ready" for project in persisted):
                break
            time.sleep(0.01)

    assert {call[0] for call in provisioner.calls} == {provisioning.id, failed.id}
    assert restarted_store.get_project_for_owner(provisioning.id, 41).status == "ready"
    assert restarted_store.get_project_for_owner(failed.id, 42).status == "ready"
