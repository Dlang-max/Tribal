# Task 3 test report

## Result

**24 Task 3 checks pass** with:

```text
.venv/bin/pytest -q tests/task3
24 passed
```

The tests exercise the actual `KubernetesProvisioner.render_resources()` against the checked-in project templates. Rendered Deployments, Services, ConfigMaps, Secrets, Ingresses, RBAC objects, NetworkPolicies, and other static Kubernetes objects are deserialized through the installed Kubernetes Python client's typed models.

Coverage includes:

- Presence of all Kubernetes kind folders and exactly one rendered Deployment, Service, ConfigMap, Secret, and Ingress.
- Worker replica count, container/service ports, startup/readiness/liveness probe paths, environment values and Secret references, and disabled worker service-account token mounting.
- Project names containing newlines, YAML-looking content, and a marker-like string remain data in the parsed ConfigMap; rendering does not create extra Kubernetes objects.
- Deployment selectors are satisfied by pod labels, and Service selectors match those labels for management, Traefik, and rendered project workers. Service `targetPort` values resolve to actual container ports; the Traefik Service targets its configured web entrypoint. Ingress backends target ports exposed by their selected Services.
- Two separately rendered project IDs get distinct worker Service selectors that select their own pod labels and cannot select the other project’s pod.
- The management Deployment imports the required ConfigMap, and its `PUBLIC_BASE_URL`, `DATABASE_PATH`, `WORKER_IMAGE`, and `K8S_TEMPLATE_ROOT` values match the current demo contract.
- Management and worker `envFrom` ConfigMap references resolve; all management, worker, shared OAuth, and per-project Secret key references point to keys present in the supplied Secret data.
- Ingress `Prefix` paths preserve `/projects/<id>` and both OAuth discovery URLs, route to the project Service on port 8000, and have no rewrite annotation.
- Management Role grants match the provisioner's actual Kubernetes calls: create/patch the four resource types, and get/create/patch Deployments for readiness and idempotent provisioning. Its RoleBinding targets only the management ServiceAccount.
- Traefik's routing permissions are a namespaced Role/RoleBinding. The worker ServiceAccount has token automount disabled and no RoleBinding subject.
- NetworkPolicies select the management and worker pods, allow ingress from Traefik on port 8000, describe DNS and HTTPS egress, and explicitly state that default KinD CNI may not enforce them.
- Static Kubernetes manifests use supported resource kinds and deserialize as Kubernetes API models; example secret manifests contain empty configuration placeholders.
- Dockerfile source/config/template packaging, Python 3.12 base, non-root runtime user, exposed port, and ownership of the configured FastMCP storage directory before switching users are checked statically.

## Limits

Docker daemon and the configured Kubernetes endpoint are unavailable in this environment. The Docker image was not built, manifests were not applied to a live cluster, and no live Traefik routing or NetworkPolicy enforcement was verified. The NetworkPolicy comments describe intended rules and do not establish isolation when the cluster CNI does not enforce policies. No live OAuth, GitHub, or Codex connection is claimed.
