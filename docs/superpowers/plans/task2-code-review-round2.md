# Task 2 code review — round 2

Scope: independent read-only review of the revised Deployment readiness
predicate in `src/tribal/kubernetes_provisioner.py`, addressing the round-one
finding. This review checks the Task 2 readiness contract and the installed
`kubernetes==37.0.2` model shape. No source edits or tests were made/run. No live
cluster behavior is claimed.

## Verdict

- **Spec: GREEN LIGHT** for the Task 2 readiness contract.
- **Quality: GREEN LIGHT** for the round-one readiness finding; no remaining
  issue found in the inspected change.

## Review evidence

`V1DeploymentStatus` in the installed Kubernetes client has optional
`observed_generation`, `replicas`, `updated_replicas`, `ready_replicas`, and
`available_replicas` fields, exposed with those snake-case Python names. The
revised predicate reads those fields, requires an integer Deployment generation
and observed generation, and returns false until the controller has observed
the current generation. The generated `V1Deployment` model requires a spec;
`spec.replicas` is optional and the code correctly applies Kubernetes' default
of one when it is `None`.

Absent status or absent counters cannot produce readiness: generation checks
fail when either generation is missing, and missing replica counters become
zero. Readiness requires a positive desired count, observed generation at least
the Deployment generation, exact total and updated replica counts, and ready
and available counts at least the desired count. This prevents the round-one
case where available old replicas alone made a changed Deployment look ready.
The API model documents `replicas`, `updated_replicas`, `ready_replicas`, and
`available_replicas` as counts of non-terminating Pods, so the total-count check
does not reject merely terminating old Pods.

The predicate therefore fails closed during stale-controller status, partial
rollout, old/new replica overlap, and missing-status cases, while accepting the
fully observed desired revision once its desired replicas are ready and
available. The check aligns with the implementation plan's requirement that
the worker be ready before provisioning returns success.

## Limitations

This is a static review of the readiness logic and installed client model. It
does not establish behavior against a running Kubernetes API or cluster.
