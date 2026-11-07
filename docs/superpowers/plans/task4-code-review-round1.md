# Task 4 code review — round 1

## Verdict

**SPEC: WITHHELD. QUALITY: WITHHELD.** Two actionable findings remain: the current wheel output reportedly omits the application package, and the runbook can attempt Traefik port-forwarding before a pod is ready.

## Review scope

Reviewed the approved Task 4 plan, `/tmp/tribal-mcp-review/task4-snapshot.md`, Task 4 implementation and test reports, current app assembly/CLI/settings/auth/project-management/worker/provisioner source, package metadata, Docker files, Kubernetes resource paths, and current README/runbook/research/work-item docs. No source or test files were changed and no tests or live services were run. The CLI help command was run locally and displayed the expected `management|worker` choices. No live startup, Docker build, cluster, OAuth, or Codex connection is claimed.

## Findings

### Important — Current wheel result does not contain the Tribal package

The coordinator reports that the current full-suite wheel packaging check fails because the generated wheel contains only distribution metadata and no `tribal` package, despite the implementation report claiming the HTML resource is present. That means the documented installed package/runtime check is not currently satisfied. `pyproject.toml` declares `src` package discovery and the source tree has `src/tribal/__init__.py`, so confirm the build is packaging the intended checkout and fix the configuration/build inputs if needed. Then verify the produced wheel contains both `tribal` modules and `tribal/templates/projects.html`, and that an isolated install can import `tribal.application` and load the template. Until that reproduction is resolved, the Task 4 packaging contract remains unverified.

### Minor — Wait for Traefik readiness before port-forwarding

The runbook applies `k8s/deployments/traefik.yaml` and `k8s/services/traefik.yaml`, then immediately tells the operator to start `kubectl port-forward service/traefik 8080:80`. If the Service has no ready endpoint yet, `kubectl port-forward` can fail. Add `kubectl -n tribal rollout status deployment/traefik` after applying the Service and before the port-forward step.

## Reviewed contracts

- Management assembly includes the session middleware, GitHub auth routes, project management routes, persistent `ProjectStore`, and `KubernetesProvisioner.from_cluster()`. Management requires the settings, session secret, database path, worker image, and template directory before startup; the documented ConfigMap/Secrets match those names.
- Management health and readiness query the actual configured SQLite path and return 503 on database errors. Router startup reconciliation is wired through the included project-management router; the Task 4 test report records an app-lifespan reconciliation check. `router.on_event` emits deprecation warnings, but no current Task 4 functionality failure was found from that usage.
- Worker construction returns the configured project worker, and its app lifespan forwards to FastMCP's mounted HTTP router lifespan. The CLI exposes the documented modes and validates `PORT` before binding `0.0.0.0`.
- The provisioner reads exactly the five fixed `k8s/{deployments,services,configmaps,secrets,ingresses}/project-worker.yaml.template` files. The runbook does not apply templates or the empty `*.example.yaml` files. Its fixed-resource commands match the existing resource folders, with management ConfigMap/Deployment/Service/Ingress deliberately delayed until after the OAuth host is configured.
- The runbook starts Traefik, port-forwarding, and the tunnel before it asks the operator to register the OAuth callback, set `PUBLIC_BASE_URL`, create credentials, or start management. Management and project callback paths are subpaths of the registered `https://HOST/` callback base; the documentation warns about wildcard matching and recommends a controlled host. Explicit `PUBLIC_BASE_URL` use and secure-cookie configuration mean callback redirects do not depend on trusting forwarded `X-Forwarded-Proto` headers.
- Error handling returns generic OAuth verification failures and does not log secrets in the reviewed assembly. Provisioning errors are persisted for display after redacting the project's token-signing key; no shared GitHub client secret is passed to the provisioner renderer.

## Validation limits

The implementation report and Task 4 test report contain local checks, but this reviewer did not run the test suite or rebuild the wheel while the packaging failure is under investigation. GitHub's callback wildcard matching was checked against its official documentation: [About the user authorization callback URL](https://docs.github.com/en/apps/creating-github-apps/registering-github-apps/about-the-user-authorization-callback-url). No live OAuth, Kubernetes, Traefik, Docker runtime, or Codex behavior is established here.
