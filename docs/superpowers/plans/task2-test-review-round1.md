# Task 2 independent test review — round 1

## TEST SPEC

**Status: one focused gap remains.** The suite exercises the real SQLite store, FastAPI management handlers, and KubernetesProvisioner with fake Kubernetes API clients. It covers login denial and CSRF rejection, owner-only list/status access, creator-only initial membership, persistence/reconciliation, owner-visible provisioning exceptions with signing-key redaction, readiness downgrade/retry, fake API create/409-patch behavior, structured YAML rendering, unsupported markers, and provisioner readiness timeout. The test-only login route issues a real signed session cookie, and no live GitHub, cluster, or Task 3 manifest claim is made. The generated template fixtures are appropriate while Task 3 manifests do not yet exist.

## Finding

**P2 — Add a route-level assertion that an unready worker cannot become `ready`.** In `src/tribal/project_management.py`, `run_provisioning()` explicitly checks the post-provision `is_ready()` result and persists `failed` when it is false (lines 48–56). Current route failure coverage makes `provision()` raise; the timeout test exercises the provisioner directly. Neither exercises the management orchestration branch where `provision()` returns normally but `is_ready()` returns false. A regression that removed or inverted this guard could mark a project ready despite no available worker while all current tests pass. Add a fake-provisioner route case that returns normally, reports false readiness, and asserts the owner sees `failed` with the expected diagnostic and that persisted status is not `ready`.

## QUALITY

**Not green-lit yet.** All 12 tests pass locally (`.venv/bin/pytest -q tests/task2`; 12 passed, one FastAPI `on_event` deprecation warning). Existing coverage is otherwise well-targeted and uses real route/store/provisioner code at the relevant boundaries. Clear the focused readiness-orchestration gap, then rerun the suite for the next review round.
