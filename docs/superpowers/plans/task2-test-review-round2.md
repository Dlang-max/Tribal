# Task 2 independent test review — round 2

## TEST SPEC

The round-one readiness gap is closed at the management API boundary. The new route test creates a project through the authenticated `POST /api/projects` handler, then polls its owner status endpoint. Its fake provisioner's `provision()` returns normally while recording `initially_ready=False`; the handler's post-provision readiness guard supplies the expected `Worker deployment did not report available replicas` diagnostic. The test checks the owner response and SQLite record both report `failed`, and explicitly verifies the record is not `ready`. This covers the orchestration branch that direct provisioner timeout coverage could not exercise.

The renderer test also covers the single-pass substitution behavior: a project name containing literal `${TOKEN_SIGNING_KEY}` is rendered into ConfigMap data unchanged, even though that marker is otherwise a valid template variable. The equality assertion on the rendered scalar would fail if replacement output were recursively scanned.

The added stale-generation provisioner test currently checks `False` while `observed_generation` is behind, then changes both `observed_generation` and `updated_replicas` before checking `True`. It therefore does not establish that readiness remains false after the controller observes the new generation but before the updated ReplicaSet has replaced the old replicas. A readiness implementation that dropped the `updated_replicas == desired_replicas` guard could still pass this regression test.

**P2 — Assert the observed-but-not-updated state.** After setting `observed_generation` to the current generation while leaving `updated_replicas` at zero, assert `is_ready()` is still false; then update the replica count and assert readiness becomes true. This directly verifies the new guard for stale ready replicas after an update.

The suite otherwise retains the route/store/provisioner boundary coverage described in the tester report: authenticated owner scoping and CSRF/input rejection, persistent status and membership, error redaction, readiness downgrade and startup reconciliation, fake Kubernetes create/patch behavior, YAML-safe structured rendering, unsupported marker rejection, and readiness timeout. Task 3's real manifests, live Kubernetes, and live GitHub OAuth are not exercised; the report makes no live-service claims.

## QUALITY

**Not green-lit yet.** `.venv/bin/pytest -q tests/task2` completed with **14 passed**. The only warning is FastAPI's deprecation notice for the router startup `on_event` hook used by reconciliation. The assertions pass, but the focused rollout regression must include the intermediate state above before test quality can be approved.
