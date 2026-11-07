# Task 2 test checkpoint

Status: **tester pass complete; ready for independent test review.**

## Completed

Tests under `tests/task2/` exercise the real `ProjectStore`, management route
handlers, and `KubernetesProvisioner` implementation:

- SQLite project records and the initial creator allowlist survive creating a
  new store instance against the same database.
- Project listing and owner-scoped lookup do not disclose another owner's
  project; each project's initial allowed GitHub IDs contain only its creator.
- The persisted incomplete-project query includes provisioning and failed
  records, excludes ready records, and retains a provisioning error.
- Anonymous API requests are rejected; project creation requires a valid CSRF
  token, rejects extra fields and blank names, and does not persist malformed
  submissions.
- Owners can create, list, and retrieve their project; another signed-in user
  sees an empty list and receives `404` for that project's status URL. Returned
  payloads omit the signing key and use the expected project MCP URL.
- Provisioning exceptions become persistent `failed` status with owner-visible
  error text; the generated per-project signing key is redacted from the error.
- A provisioner that returns without raising still leaves the project `failed`
  when its readiness check reports no available replicas.
- A project whose Deployment loses readiness is reported as `provisioning` and
  triggers a retry. Startup reconciliation retries persisted `provisioning`
  and `failed` projects after reopening the same SQLite database.
- The provisioner uses fake Kubernetes API clients to exercise create then
  conflict/patch idempotency for Deployment, Service, ConfigMap, Secret, and
  Ingress; it substitutes structured values safely, preserves a literal
  `${TOKEN_SIGNING_KEY}` included in project name data, rejects unknown source
  markers, and times out when no Deployment replicas become available.
- Deployment readiness fixtures include `metadata.generation` and the status
  observed generation, total replicas, updated replicas, ready replicas, and
  available replicas. A stale generation with one old available replica is
  rejected; observing the new generation alone remains unready until the updated
  replica is observed.

Command and result:

```text
.venv/bin/pytest -q tests/task2
14 passed, 1 warning in 0.58s
```

The warning is FastAPI's deprecation notice for the router startup `on_event`
hook used by restart reconciliation. This run includes the post-pass single-pass
template substitution hardening, round-one readiness orchestration case, and
round-two stale-replica generation regression.

## Limits

Tests create small temporary template manifests to exercise the real renderer
and provisioner against fake Kubernetes clients. Task 3's actual Kubernetes
manifests and a live cluster were not exercised. GitHub login is represented by
a test-only endpoint that issues a real signed Starlette session cookie; no live
GitHub OAuth was exercised. These results make no live-service claims.
