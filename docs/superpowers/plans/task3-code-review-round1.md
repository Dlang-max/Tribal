# Task 3 code review — round 1

## Verdict

**SPEC: GREEN LIGHT. QUALITY: GREEN LIGHT.** No actionable Task 3 findings in the reviewed snapshot.

## Review scope

Reviewed the approved Task 3 plan, `/tmp/tribal-mcp-review/task3-snapshot.md`, current `k8s/` and `docker/` files, Task 3 implementation/test reports, and current provisioner, settings, worker, and management interfaces. Task 4 entrypoint/assembly work is intentionally outside this review. No implementation, test, or configuration files were changed. No tests or live cluster validation were run by this reviewer.

## Contract and configuration checks

- `KubernetesProvisioner` consumes the five expected project templates. The templates name the per-project Deployment, Service, ConfigMap, Secret, and Ingress consistently; the provisioner adds the `tribal` namespace and project management labels before applying them.
- Project environment and secret references match `Settings.from_env()` and `build_project_worker()`: project ID/name, root public URL, allowed GitHub IDs, shared GitHub client credentials, and per-project token signing key are present. The worker has no Kubernetes API token mount.
- Prefix Ingress paths forward both `/projects/{id}` and project-specific root `/.well-known` discovery paths without rewrite annotations. These paths match the worker mount and `auth.get_well_known_routes()` contract. The management `/` route and longer project/discovery paths can coexist under Traefik's standard path routing.
- Management RBAC matches the provisioner's calls: Deployment get/create/patch for readiness and idempotent provisioning, create/patch for Services, ConfigMaps, Secrets, and Ingresses. The binding targets only the management ServiceAccount. Traefik's binding targets its own ServiceAccount and stays namespace-scoped; disabling cluster-scoped resource discovery is consistent with the annotation-based Ingresses and avoids requiring cluster-wide IngressClass/Node reads. The flag names are present in Traefik's official Kubernetes Ingress provider reference.
- Management and worker Secret/ConfigMap keys match the implementation report. The intentionally blank example credentials and invalid management public URL are operator placeholders, not silent runtime defaults; settings validation rejects missing/invalid credentials and public URLs.
- Management's database path is mounted from the PVC, and its `Recreate` strategy is appropriate for the single ReadWriteOnce claim. The checked-in KinD configuration uses the standard KinD cluster provisioning path; the absence of a `storageClassName` allows the KinD default StorageClass to bind the claim.
- NetworkPolicies select the intended pods and document the required Traefik ingress and DNS/HTTPS egress. Their comments accurately state that policy enforcement depends on the CNI; no enforcement claim is made for default KinD networking.
- Docker copies the source package and runtime Kubernetes templates, installs the locked dependencies, uses the same image/mode contract as the manifests, and runs the app as UID/GID 10001. A local wheel build confirmed that `tribal/templates/projects.html` is included in the installed package.

## Validation limits

This is static review only. The manifests were not applied to a live cluster and Traefik routing, PVC binding, image startup, OAuth, and NetworkPolicy enforcement were not verified live. The Task 3 tester separately reports 17 passing checks, including typed Kubernetes model deserialization and rendered-template contract checks; this reviewer did not rerun those tests.
