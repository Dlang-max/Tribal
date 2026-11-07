# Task 4 test report

## Coverage

- Built the real management app factory with an on-disk SQLite store and fake provisioner. Checked health, GitHub authorization URL/callback registration without contacting GitHub, unauthenticated API denial, signed-session page rendering, CSRF-protected project creation, owner identity passed to provisioning, persisted ready state, and project MCP URL assembly.
- Started the real management app through `TestClient` lifespan with an interrupted persisted project. Verified startup reconciliation provisions it and updates its stored status to ready.
- Invoked the actual `worker` CLI branch with a mocked Uvicorn server and runtime environment, then called health/readiness plus project-scoped authorization-server and protected-resource discovery routes. Verified CLI host/port selection and metadata containing the configured project prefix and public URLs.
- Patched only the Kubernetes cluster constructor to inspect management environment wiring. Verified `K8S_TEMPLATE_ROOT` is passed as the root directory as configured, with the configured worker image and public URL.
- Verified management assembly rejects missing runtime configuration and both `python -m tribal management` and `python -m tribal worker` exit nonzero with the missing `PUBLIC_BASE_URL` error when required environment variables are absent.
- Copied the package source, `pyproject.toml`, and `requirements.txt` into pytest's temporary directory, built a wheel from that isolated copy, and checked for all nine runtime modules plus `tribal/templates/projects.html` and its expected marker. Installed that wheel into a temporary target and ran `python -m tribal --help` from an isolated working directory. The isolated source copy prevents setuptools build artifacts from colliding with concurrent checkout builds.

## Results

`.venv/bin/pytest -q tests/task4` — **7 passed**, with 3 existing FastAPI `router.on_event` deprecation warnings from project-management router construction.

The wheel check verifies required application modules and the HTML template are present, then imports and runs the packaged CLI help from the installed wheel. One earlier whole-suite run overlapped a repository-root wheel build and produced a metadata-only wheel; a serial repository-root build succeeded, and the test now builds from an isolated source copy to avoid that shared-artifact race.

## Limits

These are isolated app, filesystem, and packaging checks. The provisioner is fake at the assembled app boundary; this does not establish live GitHub OAuth, Kubernetes provisioning, a Docker image build, KinD apply, Traefik routing, or an end-to-end Codex connection. No live-service result is claimed.
