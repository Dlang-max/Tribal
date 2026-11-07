# Task 3 test review — round 3

## Verdict

**TEST SPEC/QUALITY: GREEN LIGHT.** The suite closes the concrete wiring gaps raised in rounds one and two. No remaining concrete test-spec gap was found in the reviewed fixes.

## Evidence reviewed

- Round-one and round-two Task 3 test reviews and the current Task 3 test report.
- Both files under `tests/task3/` and the current checked-in Kubernetes manifests and project templates.
- `Settings`, `build_management_app()`, and `KubernetesProvisioner.render_resources()` to verify the configuration and resource contracts asserted by the tests.
- `.venv/bin/pytest -q tests/task3`: **24 passed**.

## Verified fixes

- Management, Traefik, and rendered worker Services are matched to their Deployments. Assertions require Deployment selectors to be satisfied by pod labels, Service selectors to select those labels, and Service selectors to include the Deployment selectors. A two-project render verifies each worker Service includes its own project UUID and cannot select the other project's pod.
- Management and rendered-worker Secret key references resolve against the referenced Secret's `data` or `stringData`; environment ConfigMap references also resolve. The example secrets intentionally hold empty placeholders, consistent with the reported static scope.
- Every Service target port is checked against container ports: integer targets match a container port number, and string targets match a named container port with an integer port number. The current supplied Services use named target ports. Management and worker Ingress backends are checked against their selected Services' exposed ports; Traefik's Service is checked against its configured `web` entrypoint.
- The management Deployment's referenced ConfigMap is required to contain the current `PUBLIC_BASE_URL`, `DATABASE_PATH`, `WORKER_IMAGE`, and `K8S_TEMPLATE_ROOT` values.
- Docker static checks require `HOME=/home/tribal`, create the configured FastMCP storage directory, recursively assign the home directory to UID/GID 10001 before switching to that user, and preserve the image/runtime packaging assertions. The checked Dockerfile satisfies those checks.

## Limits

These are isolated renderer and static manifest/image checks. No Docker build or live Kubernetes API-server, routing, or NetworkPolicy behavior was verified, and this verdict does not claim those outcomes.
