# Task 3 test review — round 2

## Verdict

**TEST SPEC/QUALITY: WITHHOLD GREEN LIGHT.** The round-one selector and SecretKeyRef gaps are substantially addressed, and the tests now connect rendered project resources to their selected pods and Ingress Services. Three real wiring regressions remain undetected: Service `targetPort` resolution for all workloads, project isolation in worker Service selectors, and required management ConfigMap keys.

## Evidence reviewed

- Round-one test review and current Task 3 test report.
- Both current files under `tests/task3/`.
- The checked-in management, Traefik, and project-worker Deployment, Service, Ingress, ConfigMap, and Secret manifests/templates.
- Management settings and provisioner configuration use, to identify the consequences of missing configuration.

The updated tests close the specific round-one holes: Deployment selectors are checked against pod labels; Services are checked to select the corresponding pod labels; management and rendered-worker Ingress backends are checked against their Services' exposed ports; and management/worker SecretKeyRef name/key pairs are resolved against supplied Secret manifests. The project renderer test exercises the real renderer, while management and Traefik checks inspect the checked-in resources. Traefik has no Ingress backend of its own; its Service is the controller's incoming route and needs to map to the Traefik pod's entrypoint.

## Remaining findings

### 1. Service target ports are not resolved to container ports

The Ingress checks establish that an Ingress names the selected Service and uses a Service port. They do not establish that the Service's `targetPort` reaches a port exposed by that Service's Deployment container. The management/Traefik checks do not inspect Service ports at all. The project test checks the worker Service's `port: 8000` and `targetPort: http`, and separately checks that the container exposes port 8000, but it does not assert that the worker container names that port `http`.

For example, changing the management Service target port to `http2`, the Traefik target port to `web2`, or the worker container port name from `http` while leaving its Service target port as `http` would leave the current assertions green and break routing. Check each Service port's numeric `targetPort` against a container port number, or its string `targetPort` against a named container port, for management, Traefik, and each rendered worker. Check the Traefik Service's port and target port against the controller's configured entrypoint/container port as well.

### 2. Worker Service selectors can lose project isolation

`assert_deployment_matches_service` only verifies that the Service selector's key/value pairs occur on the Deployment's pod template. It does not require the Service selector to include the Deployment selector's distinguishing labels. The rendered worker Service selector can therefore drop `tribal.dev/project-id` and still match the sample worker pod; it would then select every project-worker pod, potentially sending requests for one project to another project's worker. The current test passes this miswiring.

For each rendered project, require its Service selector to include the Deployment selector (or assert the expected project-ID selector explicitly), in addition to confirming that the pod template satisfies both selectors. This preserves per-project routing instead of merely proving that at least one pod matches.

### 3. Management ConfigMap values are not checked against required settings

The management helper verifies that its `envFrom.configMapRef` names an available ConfigMap with nonempty data, but does not assert the required management keys are present. Removing `DATABASE_PATH`, `WORKER_IMAGE`, or `K8S_TEMPLATE_ROOT` from the referenced ConfigMap leaves unrelated data and passes the test, even though management mode requires those settings. The management `PUBLIC_BASE_URL` also needs to be supplied through the ConfigMap. Worker ConfigMap values receive stronger checks in `test_worker_environment_references_project_config_and_shared_github_secret`.

Assert the management Deployment imports the intended ConfigMap and that its data contains the management settings required by the current settings/application code. The existing SecretKeyRef resolution checks cover the management and worker secret keys; Traefik has no ConfigMap or Secret refs to resolve.

## Limits

This was a read-only test review. The reported 21 checks were not rerun in this review, and no source or test files were edited. No live Kubernetes API-server, Docker build, Traefik routing, or cluster behavior is claimed.
