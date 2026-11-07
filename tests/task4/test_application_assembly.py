import base64
import json
import os
import shutil
import subprocess
import sys
import time
import zipfile
from pathlib import Path

from fastapi.testclient import TestClient
from itsdangerous import TimestampSigner

from tribal import __main__ as tribal_cli
from tribal import application
from tribal.project_store import ProjectStore
from tribal.settings import Settings, SettingsError


PUBLIC_BASE_URL = "https://tribal.example"
SESSION_KEY = "task-four-session-key-with-enough-entropy-for-tests"
CSRF_TOKEN = "task-four-csrf-token-long-enough-for-a-valid-session"
PROJECT_ID = "e1b10fda-5967-4db5-86a8-c08008a0e162"


def settings(*, project_id=None, project_name=None):
    return Settings(
        public_base_url=PUBLIC_BASE_URL,
        github_client_id="test-client-id",
        github_client_secret="test-client-secret",
        token_signing_key="test-worker-signing-key",
        session_signing_key=SESSION_KEY,
        project_id=project_id,
        project_name=project_name,
        allowed_github_ids=frozenset({41}) if project_id else frozenset(),
    )


def signed_session_cookie(identity_id=41, login="alice"):
    session = {
        "github_identity": {
            "github_id": identity_id,
            "login": login,
            "name": None,
            "email": None,
        },
        "csrf_token": CSRF_TOKEN,
    }
    encoded = base64.b64encode(json.dumps(session).encode("utf-8"))
    return TimestampSigner(SESSION_KEY).sign(encoded).decode("utf-8")


class FakeProvisioner:
    def __init__(self, *, ready=True):
        self.ready = ready
        self.provision_calls = []
        self.readiness_calls = []

    def provision(self, project_id, name, allowed_github_ids, token_signing_key):
        self.provision_calls.append((project_id, name, allowed_github_ids, token_signing_key))

    def is_ready(self, project_id):
        self.readiness_calls.append(project_id)
        return self.ready


def wait_for_status(client, status_url, expected, timeout=2):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        response = client.get(status_url)
        assert response.status_code == 200
        payload = response.json()
        if payload["status"] == expected:
            return payload
        time.sleep(0.01)
    raise AssertionError(f"project did not reach {expected!r}")


def test_management_factory_assembles_auth_project_routes_and_real_store_boundary(tmp_path):
    provisioner = FakeProvisioner()
    store = ProjectStore(tmp_path / "assembled.sqlite3")
    app = application.build_management_app(
        settings(), store=store, provisioner=provisioner
    )

    with TestClient(app, base_url=PUBLIC_BASE_URL, follow_redirects=False) as client:
        assert client.get("/healthz").json() == {"status": "ok"}
        login = client.get("/auth/login")
        assert login.status_code == 302
        assert "github.com/login/oauth/authorize" in login.headers["location"]
        assert "auth%2Fcallback" in login.headers["location"]
        assert client.get("/api/projects").status_code == 401
        client.cookies.clear()
        client.cookies.set(
            "tribal_session", signed_session_cookie(), domain="tribal.example", path="/"
        )
        page = client.get("/")
        assert page.status_code == 200
        assert "alice" in page.text
        assert CSRF_TOKEN in page.text

        created = client.post(
            "/api/projects",
            json={"name": "Assembly test"},
            headers={"X-CSRF-Token": CSRF_TOKEN},
        )
        assert created.status_code == 202
        result = created.json()
        ready = wait_for_status(client, result["status_url"], "ready")

    assert ready["mcp_url"] == f"{PUBLIC_BASE_URL}/projects/{result['id']}/mcp"
    assert provisioner.provision_calls[0][:3] == (result["id"], "Assembly test", frozenset({41}))
    assert store.get_project_for_owner(result["id"], 41).status == "ready"


def test_management_factory_lifespan_reconciles_persisted_projects(tmp_path):
    database = tmp_path / "persisted.sqlite3"
    store_before_restart = ProjectStore(database)
    pending = store_before_restart.create_project(
        "Interrupted project",
        41,
        "alice",
        f"{PUBLIC_BASE_URL}/projects/{PROJECT_ID}/mcp",
        "persisted-project-signing-key",
        project_id=PROJECT_ID,
    )
    provisioner = FakeProvisioner()
    app = application.build_management_app(
        settings(),
        store=ProjectStore(database),
        provisioner=provisioner,
    )

    with TestClient(app, base_url=PUBLIC_BASE_URL):
        deadline = time.monotonic() + 2
        while time.monotonic() < deadline:
            refreshed = store_before_restart.get_project_for_owner(pending.id, 41)
            if refreshed.status == "ready":
                break
            time.sleep(0.01)

    assert provisioner.provision_calls[0][:3] == (
        PROJECT_ID,
        "Interrupted project",
        frozenset({41}),
    )
    assert store_before_restart.get_project_for_owner(PROJECT_ID, 41).status == "ready"


def test_worker_cli_reads_runtime_env_and_serves_project_metadata_without_rewrites(monkeypatch):
    for name, value in {
        "PUBLIC_BASE_URL": PUBLIC_BASE_URL,
        "GITHUB_CLIENT_ID": "test-client-id",
        "GITHUB_CLIENT_SECRET": "test-client-secret",
        "TOKEN_SIGNING_KEY": "test-worker-signing-key",
        "PROJECT_ID": PROJECT_ID,
        "PROJECT_NAME": "Compiler notes",
        "ALLOWED_GITHUB_IDS": "41",
    }.items():
        monkeypatch.setenv(name, value)
    monkeypatch.setenv("PORT", "8123")
    monkeypatch.setattr(sys, "argv", ["tribal", "worker"])
    launched = {}

    def capture_server(app, **kwargs):
        launched["app"] = app
        launched.update(kwargs)

    monkeypatch.setattr(tribal_cli.uvicorn, "run", capture_server)
    tribal_cli.main()
    worker = launched["app"]
    assert launched["host"] == "0.0.0.0"
    assert launched["port"] == 8123

    with TestClient(worker, base_url=PUBLIC_BASE_URL) as client:
        assert client.get("/healthz").status_code == 200
        assert client.get("/readyz").status_code == 200
        authorization = client.get(
            f"/.well-known/oauth-authorization-server/projects/{PROJECT_ID}"
        )
        protected = client.get(
            f"/.well-known/oauth-protected-resource/projects/{PROJECT_ID}/mcp"
        )

    assert authorization.status_code == 200
    assert authorization.json()["issuer"] == f"{PUBLIC_BASE_URL}/projects/{PROJECT_ID}"
    assert protected.status_code == 200
    assert protected.json()["resource"] == f"{PUBLIC_BASE_URL}/projects/{PROJECT_ID}/mcp"


def test_management_factory_uses_configured_template_root_as_k8s_root(monkeypatch, tmp_path):
    captured = {}

    def fake_from_cluster(**kwargs):
        captured.update(kwargs)
        return FakeProvisioner()

    monkeypatch.setattr(
        application.KubernetesProvisioner,
        "from_cluster",
        fake_from_cluster,
    )
    for name, value in {
        "PUBLIC_BASE_URL": PUBLIC_BASE_URL,
        "GITHUB_CLIENT_ID": "client-id",
        "GITHUB_CLIENT_SECRET": "client-secret",
        "TOKEN_SIGNING_KEY": "token-key",
        "SESSION_SIGNING_KEY": SESSION_KEY,
        "DATABASE_PATH": str(tmp_path / "runtime.sqlite3"),
        "WORKER_IMAGE": "tribal-mcp-demo:local",
        "K8S_TEMPLATE_ROOT": str(Path(__file__).parents[2] / "k8s"),
    }.items():
        monkeypatch.setenv(name, value)

    application.build_management_app()

    assert captured["template_root"] == str(Path(__file__).parents[2] / "k8s")
    assert captured["worker_image"] == "tribal-mcp-demo:local"
    assert captured["public_base_url"] == PUBLIC_BASE_URL


def test_management_factory_refuses_missing_runtime_configuration(monkeypatch):
    for name in (
        "PUBLIC_BASE_URL",
        "GITHUB_CLIENT_ID",
        "GITHUB_CLIENT_SECRET",
        "TOKEN_SIGNING_KEY",
        "SESSION_SIGNING_KEY",
        "DATABASE_PATH",
        "WORKER_IMAGE",
        "K8S_TEMPLATE_ROOT",
    ):
        monkeypatch.delenv(name, raising=False)

    try:
        application.build_management_app()
    except SettingsError as exc:
        assert "PUBLIC_BASE_URL" in str(exc)
    else:
        raise AssertionError("management app unexpectedly built without configuration")


def test_cli_modes_exit_with_configuration_error_when_env_is_incomplete():
    required_environment = {
        "PUBLIC_BASE_URL",
        "GITHUB_CLIENT_ID",
        "GITHUB_CLIENT_SECRET",
        "TOKEN_SIGNING_KEY",
        "SESSION_SIGNING_KEY",
        "DATABASE_PATH",
        "WORKER_IMAGE",
        "K8S_TEMPLATE_ROOT",
    }
    env = {
        key: value
        for key, value in os.environ.items()
        if key not in required_environment
    }
    for mode in ("management", "worker"):
        result = subprocess.run(
            [sys.executable, "-m", "tribal", mode],
            cwd=Path(__file__).parents[2],
            env=env,
            capture_output=True,
            text=True,
        )

        assert result.returncode != 0
        assert "PUBLIC_BASE_URL must be set" in result.stderr


def test_wheel_contains_runtime_and_template_assets(tmp_path):
    root = Path(__file__).parents[2]
    source_copy = tmp_path / "package-source"
    output = tmp_path / "wheelhouse"
    source_copy.mkdir()
    shutil.copytree(root / "src", source_copy / "src")
    shutil.copy2(root / "pyproject.toml", source_copy / "pyproject.toml")
    shutil.copy2(root / "requirements.txt", source_copy / "requirements.txt")
    subprocess.run(
        [
            sys.executable,
            "-m",
            "pip",
            "wheel",
            "--no-deps",
            "--wheel-dir",
            str(output),
            str(source_copy),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    wheels = list(output.glob("tribal-*.whl"))
    assert len(wheels) == 1
    with zipfile.ZipFile(wheels[0]) as wheel:
        members = set(wheel.namelist())
        required_modules = {
            "tribal/__init__.py",
            "tribal/__main__.py",
            "tribal/application.py",
            "tribal/authentication.py",
            "tribal/project_worker.py",
            "tribal/settings.py",
            "tribal/project_management.py",
            "tribal/project_store.py",
            "tribal/kubernetes_provisioner.py",
        }
        assert required_modules <= members
        assert "tribal/templates/projects.html" in members
        markup = wheel.read("tribal/templates/projects.html").decode("utf-8")
    assert "{{csrf_token}}" in markup

    installed = tmp_path / "installed-wheel"
    subprocess.run(
        [
            sys.executable,
            "-m",
            "pip",
            "install",
            "--no-deps",
            "--target",
            str(installed),
            str(wheels[0]),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    env = os.environ.copy()
    env["PYTHONPATH"] = str(installed)
    cli = subprocess.run(
        [sys.executable, "-m", "tribal", "--help"],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
    )
    assert cli.returncode == 0
    assert "management" in cli.stdout and "worker" in cli.stdout
