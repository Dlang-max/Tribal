# GitHub-authenticated project MCP servers: implementation status

Updated: 2026-11-07. This document replaces the earlier four-item shared-app proposal with the approved local KinD implementation tasks. It is a status record, not proof of live deployment or OAuth.

## Approved topology

One container image runs a GitHub-authenticated management app and one stateless MCP worker per project. Management stores project records in SQLite and provisions each worker's Deployment, Service, ConfigMap, Secret, and Ingress. Workers validate FastMCP GitHub OAuth tokens and check the numeric GitHub account ID against that project's allowlist on every tool call. The sample tool is explicitly labeled; the knowledge base is not connected.

## Task status

- **Task 1 — authentication and worker:** implemented. Provides Authlib browser login/session/CSRF helpers, FastMCP GitHub OAuth workers, health routes, and the sample-context tool. See [implementation report](../superpowers/plans/task1-implementation-report.md). The latest task test report records its checks; independent review status is tracked in the checkpoint.
- **Task 2 — management and provisioning:** implemented. Provides the SQLite project store, project page/API, provision orchestration, readiness checks, and YAML-safe worker resource renderer. See [implementation report](../superpowers/plans/task2-implementation-report.md).
- **Task 3 — Kubernetes and image:** implemented. Provides fixed manifests, five project worker templates, least-scope namespaced RBAC, network policies, and the shared Docker image. See [implementation report](../superpowers/plans/task3-implementation-report.md).
- **Task 4 — assembly and instructions:** implemented in `src/tribal/application.py` and `src/tribal/__main__.py`; this task adds the README and [Codex connection walkthrough](../connecting-codex-to-tribal.md). The [implementation report](../superpowers/plans/task4-implementation-report.md) records local checks and limits.

## Operational limits

Use a controlled dedicated HTTPS callback host because GitHub wildcard callback matching permits project OAuth subpaths. Quick Tunnels are ephemeral, intended for development, and do not support SSE; this app uses stateless JSON responses over Streamable HTTP. The default KinD CNI may not enforce NetworkPolicies. Enterprise SAML, roles, invitations, real graph data, and production hosting remain out of scope.

Do not apply the empty `*.example.yaml` Secrets. Create the OAuth and signing Secrets from operator-supplied values, keep them out of version control, and set the public origin before starting management. See the walkthrough for exact commands and cleanup.

## Historical proposal

The former four items proposed a single shared-app MCP route, a runtime-neutral store, and a generic hosted demonstration. The approved topology above supersedes those assumptions; the backlog is retained at this path for continuity, but the old architecture is no longer an active proposal.
