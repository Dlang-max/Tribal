# Task 2 implementation report

## Implemented

- `src/tribal/project_store.py` persists project UUID, name, owner GitHub ID/login, MCP URL, status, provisioning error, and a per-project token signing key in SQLite. Membership is a separate table initialized with the creator as the only member. Connections are per operation, with WAL mode and a busy timeout. Records survive management restarts.
- `src/tribal/project_management.py` exposes a minimal signed-in management page and APIs: `GET /`, `GET /api/projects`, CSRF-protected `POST /api/projects`, and owner-only `GET /api/projects/{project_id}`. Unauthenticated API calls return 401; nonexistent and non-owned IDs both return 404. The create response is `202` with `id`, `status`, and `status_url`. Responses omit signing keys.
- The management router uses Task 1's session identity and CSRF helpers. Creation validates a 1–100 character project name, generates the UUID and independent signing key on the server, persists the creator-only member row, and schedules provisioning asynchronously.
- Provisioning runs in a thread so Kubernetes calls do not block the ASGI loop. Status is persisted as `provisioning`, then `ready` only after the provisioner returns and a fresh live readiness check confirms available replicas. Exceptions become persisted `failed` status with clipped, signing-key-redacted error details. A previously ready record is downgraded and reprovisioned when a list/detail readiness check detects an unavailable Deployment.
- Deployment readiness is fail-closed against stale ReplicaSets: the controller must observe the current generation, desired replicas must be positive, current replicas must equal desired (no old rollout replicas pending), updated replicas must equal desired, and ready/available replicas must each meet desired.
- FastAPI router startup schedules reconciliation for persisted `provisioning` and `failed` records. Repeated resource application is idempotent through Kubernetes create/patch behavior.
- `src/tribal/kubernetes_provisioner.py` reads only the five explicit Task 3 template paths under `k8s/{deployments,services,configmaps,secrets,ingresses}/project-worker.yaml.template`. It parses with `yaml.safe_load` before substituting only parsed scalar/key values; unknown markers and unexpected/duplicate resource kinds are rejected. Inputs are project ID/name, public base URL, creator allowlist, per-project token signing key, and operator-configured worker image. The shared GitHub secret is not passed into the renderer and must be referenced from the worker Pod through `SecretKeyRef`.
- `src/tribal/templates/projects.html` provides the project form/list UI, CSRF header, status polling, visible provisioning errors, and GitHub sign-in/sign-out links. Project names and error strings are rendered through DOM text nodes.
- Added direct pins `kubernetes==37.0.2` and `PyYAML==6.0.3` to `requirements.txt`; refreshed `requirements.lock` with the Kubernetes client dependencies.

## Interfaces for Task 4

- Add auth middleware with `add_management_session_middleware(app, settings)`, include `build_management_auth_routes(settings)`, then include `build_project_management_routes(store, provisioner, settings.public_base_url)`.
- Construct persistent storage as `ProjectStore(database_path)`.
- Construct the real provisioner with `KubernetesProvisioner.from_cluster(public_base_url=settings.public_base_url, worker_image=...)`. `WORKER_IMAGE` must be set by the operator or supplied explicitly.
- Injected provisioners can implement synchronous `provision(project_id, name, allowed_github_ids, token_signing_key)` and `is_ready(project_id)` methods; both are called off the event loop.
- Add `tribal = ["templates/*.html"]` under setuptools package data in `pyproject.toml` when Task 4 finalizes packaging. That Task 1-owned file is intentionally unchanged here; there is no source-copy workaround.

## Checks performed

- `.venv/bin/python -m py_compile src/tribal/project_store.py src/tribal/kubernetes_provisioner.py src/tribal/project_management.py` completed successfully.
- `.venv/bin/pytest -q tests/task2` reported 14 passing checks for persistence/ownership/membership, anonymous and CSRF denial, project API behavior, error redaction, readiness downgrade/retry, startup reconciliation, template safety, idempotent resource application, readiness timeout, and stale-generation/old-replica rejection. The tester noted FastAPI's deprecation warning for router `on_event("startup")`; migration to lifespan integration remains a small follow-up if the assembled app requires it.
- The final renderer single-pass substitution hardening and Deployment rollout readiness predicate both compile; the tester reran the full suite after these changes.
- `kubernetes==37.0.2` installed successfully in the existing Python 3.12 virtual environment. No live Kubernetes cluster, Docker image, GitHub credentials, or end-to-end Codex connection was available for this task.

## Pending integration and review

- Task 3 still needs to provide exactly one each of Deployment, Service, ConfigMap, Secret, and Ingress at the template paths above. The Deployment name must be `tribal-project-${PROJECT_ID}` and its worker container must use `/readyz`; worker container env must consume the shared GitHub secret by `SecretKeyRef`.
- Task 4 must include the router and middleware, choose the persistent database path, configure `WORKER_IMAGE`, and add package data as described above.
- Task 2 implementation review round 1 identified a stale-revision readiness issue; the predicate was tightened as described above. Fresh implementation review and independent test review remain pending. This report records implementation and local checks, not review approval or live-cluster acceptance.
