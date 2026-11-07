# Task 2 code review — round 1

Scope: static review of the frozen Task 2 snapshot and current source against
`2026-11-07-kubernetes-project-mcp-demo.md`. Task 3 templates are not present,
so this review does not assess their contents. No source changes or tests were
made/run. The implementation report records the tester's 12 passing checks;
this review is independent of those checks. No live cluster, GitHub OAuth, or
end-to-end behavior is claimed.

## Verdict

- **Spec: GREEN LIGHT** for the implemented Task 2 route, ownership, persistence,
  provisioning, retry, and renderer contracts, subject to the Task 3 template
  contract still being satisfied.
- **Quality: HOLD** on one readiness correctness issue below. It can mark a
  project ready while Kubernetes is still serving the previous Deployment
  revision after a patch/reconcile.

## Finding

### P2 — Deployment readiness can accept old replicas after a template patch

**Location:** `src/tribal/kubernetes_provisioner.py:168-178`.

`is_ready()` accepts a Deployment when `available_replicas >= spec.replicas`.
Kubernetes `availableReplicas` can include available Pods from an older
ReplicaSet while a rollout is in progress. It does not establish that the
current Deployment generation was observed or that the desired revision's
replicas are updated. `provision()` applies the Deployment via create-or-patch
and then calls this check; therefore an already-available old worker can make
provisioning return success immediately after a changed Deployment template
is patched. `run_provisioning()` then persists `ready` based on the same check.

**Reproduction:** start with project Deployment revision A at one available
replica; make a desired template change that rolls it to revision B (for
example, change the configured worker image); invoke `provision()` while the
old replica remains available and before B becomes available. The current
predicate sees one available replica against one desired replica and returns
ready, even though B has not become available yet.

Use the Deployment's observed generation and updated replica count in the
readiness predicate (and still require available replicas) so the status means
the desired revision has become available. This matters on retry/reconciliation
where resources already exist; new UUID creation alone does not exercise it.

## Reviewed areas with no finding

- Management mutations require a signed-in session and session-bound CSRF
  token. Owner scoping is applied in both project listing and detail lookup;
  unauthorized and nonexistent IDs share the 404 response.
- The initial project membership is only the verified creator ID. The
  management payload does not expose the stored signing key.
- Provisioning failures and readiness-check errors redact the exact persisted
  per-project signing key before saving an owner-visible, length-limited error.
- The SQLite file-backed lifecycle persists projects and membership; startup
  schedules records still in `provisioning` or `failed` for reconciliation.
- The renderer reads only the fixed five template paths, uses `yaml.safe_load`
  before substitution, makes a single substitution pass, rejects unknown or
  malformed markers, and enforces one resource per expected kind. Create/409
  patch is a reasonable idempotent upsert for the expected fixed resource set.
- `kubernetes==37.0.2` and `PyYAML==6.0.3` are direct exact pins and appear in
  the refreshed lock file. Task 3's actual manifests and live readiness remain
  outside this review.
