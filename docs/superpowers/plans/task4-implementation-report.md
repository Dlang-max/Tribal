# Task 4 implementation report

## Implemented

- Added `src/tribal/application.py` with `build_management_app()` and `build_worker_app()`. Management assembles Task 1's Authlib session/auth routes, Task 2's project router/store, and Task 2's real Kubernetes provisioner. Callers can inject settings, a store, and a provisioner; production construction uses required environment settings and real adapters.
- Added `src/tribal/__main__.py`: `python -m tribal management|worker` binds to `0.0.0.0`, using `PORT` or `8000`. Invalid/missing runtime configuration fails before the server starts. Management health and readiness return success only while its actual SQLite database can answer a query.
- Added setuptools package data for `src/tribal/templates/*.html` so the management UI ships in wheels.
- Added `README.md` and `docs/connecting-codex-to-tribal.md` with fixed KinD setup commands, non-committed secret creation, image loading, tunnel and OAuth setup, Codex add/login/tool steps, project cleanup, and scope limits.
- Updated the authentication research and work-item documents to describe the selected per-project worker topology and identify the earlier shared-app plan as superseded for this local demo.

## Local checks

- Built a wheel with `python -m pip wheel --no-deps` in the repository's Python 3.12 virtual environment.
- Installed the wheel into an isolated target directory and confirmed `tribal/templates/projects.html` is present in package resources.
- Ran the installed package's `python -m tribal --help` successfully.
- `python -m compileall -q src/tribal` completed successfully.

These checks do not exercise a live Docker image, KinD cluster, GitHub OAuth flow, or Codex MCP connection. No tests were authored or run by this implementor. See separate Task 4 tester/reviewer reports for integration test results.

## Configuration contract

Management requires `PUBLIC_BASE_URL`, `GITHUB_CLIENT_ID`, `GITHUB_CLIENT_SECRET`, `TOKEN_SIGNING_KEY`, `SESSION_SIGNING_KEY`, `DATABASE_PATH`, `WORKER_IMAGE`, and `K8S_TEMPLATE_ROOT`. It constructs `ProjectStore` and `KubernetesProvisioner.from_cluster()` unless dependencies are injected. The documented cluster values are `/data/tribal.sqlite3`, `tribal-mcp-demo:local`, and `/app/k8s`. Worker mode uses the existing worker settings contract.

## Code review round 1 adjustment

The reviewer found that the walkthrough could start the Traefik port-forward before its Deployment was ready. Added an explicit `kubectl rollout status deployment/traefik --timeout=120s` after applying the Deployment and Service. The review report is `task4-code-review-round1.md`.
