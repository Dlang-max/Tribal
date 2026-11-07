# Task 3 test review — round 1

## Verdict

**TEST SPEC/QUALITY: WITHHOLD GREEN LIGHT.** The suite has meaningful renderer coverage, but it does not assert the cross-resource selector relationship that makes each provisioned worker reachable. A selector regression can leave the Deployment healthy while the Service has no endpoints and the Ingress returns 503, with all 17 checks still passing.

## Evidence reviewed

- Task 3 plan, implementation report, and test report.
- Both files under `tests/task3/` (17 parameterized/concrete checks as reported).
- `KubernetesProvisioner.render_resources()` and all five project templates.
- Management/Traefik manifests, RBAC, NetworkPolicies, Dockerfile, and worker route implementation/tests.

The project tests call the actual `render_resources()` implementation on checked-in templates, parse the results as YAML, and deserialize them through the installed Kubernetes client models. The current rendered Deployment pod labels and Deployment selector agree; the Service selector also agrees with those pod labels. The Ingress paths and backends currently match the worker's project mount and discovery routes. This is materially better than testing placeholder strings alone.

However, the tests never compare `Service.spec.selector` to `Deployment.spec.template.metadata.labels`, or ensure the Deployment's `spec.selector.matchLabels` is satisfied by those pod labels. The Service test checks only its port and target port; the Ingress test checks the Service name/port. If a future template edit changes a project-ID or app label on just one side, no endpoints are selected and the public worker route fails despite the current assertions passing.

There is a related SecretRef coverage hole: the project test checks the referenced Secret names, but not the `secretKeyRef.key` values against the rendered per-project Secret and shared GitHub Secret key sets. It also does not inspect the management Deployment's four SecretRefs against the two checked-in example Secrets. The current key names do match. A wrong key is accepted by the API server and makes the pod fail configuration at startup, so checking the ref-name/key pairs would make this part of the demo contract robust.

## Other quality notes

- The exact management Role permissions agree with the current provisioner calls (`create`, conflict `patch`, and Deployment `get` for readiness). The Traefik Role is namespaced, and the worker ServiceAccount has no binding and disables token automount.
- NetworkPolicy tests check pod selectors, Traefik ingress, and DNS/HTTPS ports. The manifests and report clearly say that default KinD CNI may not enforce them; they do not claim isolation.
- Kubernetes client deserialization is useful shape coverage, but it is not API-server validation and does not establish that a cluster accepts/runs the objects.
- Docker assertions are explicitly static. The report correctly says no image build, cluster apply, or live routing/enforcement was verified. No live Docker or cluster result is inferred here.

## Required test-review fix

Add cross-resource assertions for each rendered project set that:

1. Require the Deployment selector to be a subset of its pod-template labels.
2. Require the Service selector to match the rendered Deployment pod-template labels (or at least select that pod template).
3. Resolve every worker `secretKeyRef` against its source Secret and assert the key exists; check the management Deployment refs against the shared and management example Secrets as well.

These are static checks and do not require Docker or a live cluster. The first selector relationship is the blocking gap for this review round.

## Limits

This was a read-only review of source, manifests, and the supplied test report. The reported 17 tests were not rerun. Docker daemon and Kubernetes endpoints are unavailable per the execution checkpoint, so no live image, API-server, ingress, or NetworkPolicy claim is made.
