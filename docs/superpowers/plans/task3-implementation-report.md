# Task 3 implementation report

## Implemented

- Added kind-grouped Kubernetes resources under `k8s/`: the `tribal` namespace, management and Traefik Deployments/Services/ServiceAccounts, a persistent management PVC, management ConfigMap and secret examples, namespaced Roles/RoleBindings, Ingresses, and NetworkPolicies.
- Added the five exact project-worker templates consumed by `KubernetesProvisioner`: `deployments/project-worker.yaml.template`, `services/project-worker.yaml.template`, `configmaps/project-worker.yaml.template`, `secrets/project-worker.yaml.template`, and `ingresses/project-worker.yaml.template`. Each renders exactly one Deployment, Service, ConfigMap, Secret, and standard Ingress. Project IDs/names and configured values remain parsed-scalar substitutions; the Ingress uses `Prefix` paths without rewriting and forwards `/projects/{id}` and both project-specific `/.well-known` endpoints unchanged.
- Management provisions only the namespaced resource operations its source uses: create/patch workers and get Deployments for readiness. Traefik uses a namespaced Role and watches only `tribal`; its `IngressClass` annotation is fixed to `traefik`, and `disableClusterScopeResources=true` avoids cluster-scoped IngressClass/Node reads. Workers use the shared `tribal-github-oauth` Secret through explicit `SecretKeyRef`s and a per-project signing Secret created by the provisioner. Worker ServiceAccounts disable token automount.
- Added management SQLite persistence at `/data/tribal.sqlite3` on a 1 GiB PVC. Management uses `tribal-management-auth` for `TOKEN_SIGNING_KEY` and `SESSION_SIGNING_KEY`. `PUBLIC_BASE_URL` has an intentionally invalid placeholder so the Task 4 application settings fail rather than silently run with an unconfigured public URL. `WORKER_IMAGE` is `tribal-mcp-demo:local` with `imagePullPolicy: Never` for a KinD-loaded local image.
- Traefik is pinned to `traefik:v3.7.17`, runs the standard Kubernetes Ingress provider, and is reachable only through its `ClusterIP` Service. Local access uses `kubectl port-forward service/traefik ...`; no NodePort or LoadBalancer opens a cluster port. Project routes and the management root route share the same hostless Ingress entrypoint; longest-path routing preserves worker prefixes while `/` serves management.
- Added management and worker NetworkPolicies for ingress from Traefik and DNS/HTTPS egress. Comments state that default KinD CNI may not enforce these policies, so they do not claim isolation without an enforcing CNI.
- Added `docker/Dockerfile` for Python 3.12, pinned `requirements.lock`, the Tribal package, and runtime `k8s/` templates. It creates a UID/GID 10001-owned home and FastMCP data directory, sets `HOME=/home/tribal` and `FASTMCP_HOME=/home/tribal/.local/share/fastmcp` for FastMCP's default OAuth registration storage, sets `K8S_TEMPLATE_ROOT=/app/k8s`, and leaves management/worker mode selection to the Kubernetes workload command. `docker/Dockerfile.dockerignore` excludes tests, docs, virtualenv and frontend files from a repository-root build context.

## Frozen Task 4 interface

- Image: `tribal-mcp-demo:local`; build context is the repository root with `docker/Dockerfile`.
- Namespace: `tribal`.
- Container invocation: `python -m tribal management` for the management Deployment and `python -m tribal worker` for project Deployments.
- Management listens on port `8000`, uses `/healthz`, reads ConfigMap `tribal-management` and Secret `tribal-management-auth`, and gets the shared OAuth Secret `tribal-github-oauth`.
- Management ConfigMap keys: `PUBLIC_BASE_URL`, `DATABASE_PATH=/data/tribal.sqlite3`, `WORKER_IMAGE=tribal-mcp-demo:local`, and `K8S_TEMPLATE_ROOT=/app/k8s`.
- Shared GitHub Secret `tribal-github-oauth` keys: `GITHUB_CLIENT_ID`, `GITHUB_CLIENT_SECRET`. Management auth Secret `tribal-management-auth` keys: `TOKEN_SIGNING_KEY`, `SESSION_SIGNING_KEY`. The project worker template references the shared Secret via those keys; the provisioner creates `tribal-project-${PROJECT_ID}-auth` with `TOKEN_SIGNING_KEY`.
- Management Service/Ingress names are `tribal-management`; project names are `tribal-project-${PROJECT_ID}`; Traefik Service/Deployment/ServiceAccount names are `traefik`.
- Management and worker HTTP service/target port is `8000`; worker readiness is `/readyz`, health is `/healthz`. Traefik's ClusterIP Service port is `80` and its pod listens on `8000`.
- Management Role `tribal-project-provisioner` grants `apps/deployments` get/create/patch, core `services/configmaps/secrets` create/patch, and `networking.k8s.io/ingresses` create/patch. Traefik Role `traefik-ingress` reads/watches services, endpoints, secrets, EndpointSlices and Ingresses and updates Ingress status, all in `tribal` only.

The two `*.example.yaml` Secret manifests intentionally contain empty values. Replace them with real, independent management signing keys and GitHub OAuth credentials before applying them. Do not use placeholder credentials for a running demo.

## Checks and limits

- Static YAML parsing succeeded for 20 fixed `.yaml` files.
- The source `KubernetesProvisioner.render_resources` rendered all five project resource kinds from the exact configured template paths; a static check confirmed the project Deployment name and disabled worker ServiceAccount token automount.
- Inspected the installed FastMCP 4.1.6 settings and OAuth proxy storage code: settings use the `FASTMCP_` environment prefix for `home`, and the default OAuth proxy store creates directories below `settings.home/oauth-proxy`. The Dockerfile now provides that path under a directory writable by the non-root runtime UID.
- No tests were authored or run by this implementor. No Docker image build, KinD apply, port-forward, GitHub login, or live OAuth/MCP exchange was performed because Docker/Kubernetes and OAuth credentials are unavailable in the current environment.
- Traefik provider/watch configuration follows the official [Kubernetes Ingress provider reference](https://doc.traefik.io/traefik/reference/install-configuration/providers/kubernetes/kubernetes-ingress/). Version `v3.7.17` was the latest stable Traefik release listed by the [official release page](https://github.com/traefik/traefik/releases) at implementation time.
