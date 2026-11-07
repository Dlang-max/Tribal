# Connect Codex to Tribal

This guide runs the local KinD demo. It provisions separate project Deployments and Services from one image. The tool returns clearly labeled sample context; the remote knowledge base and graph are not connected.

## Prerequisites

Install Docker, KinD, `kubectl`, `cloudflared`, Python 3.12, and Codex CLI. Docker and Kubernetes must be running. GitHub OAuth credentials are required for browser sign-in and MCP authorization.

## Build and start KinD

From the repository root:

```sh
kind create cluster --config k8s/kind.yaml
docker build -f docker/Dockerfile -t tribal-mcp-demo:local .
kind load docker-image tribal-mcp-demo:local
kubectl apply -f k8s/namespaces/tribal.yaml
kubectl apply -f k8s/service-accounts/management.yaml
kubectl apply -f k8s/service-accounts/project-worker.yaml
kubectl apply -f k8s/service-accounts/traefik.yaml
kubectl apply -f k8s/rbac/management-role.yaml
kubectl apply -f k8s/rbac/management-rolebinding.yaml
kubectl apply -f k8s/rbac/traefik-role.yaml
kubectl apply -f k8s/rbac/traefik-rolebinding.yaml
kubectl apply -f k8s/persistent-volume-claims/management.yaml
kubectl apply -f k8s/network-policies/management.yaml
kubectl apply -f k8s/network-policies/project-workers.yaml
kubectl apply -f k8s/deployments/traefik.yaml
kubectl apply -f k8s/services/traefik.yaml
kubectl -n tribal rollout status deployment/traefik --timeout=120s
```

These are the fixed shared resources. Project worker manifests are templates, not applied directly. The `*.example.yaml` Secret files contain empty values and are examples only; never apply them unchanged.

## Create credentials and set the public URL

Start the port-forward in a terminal and leave it running:

```sh
kubectl -n tribal port-forward service/traefik 8080:80
```

In another terminal, start a Cloudflare Quick Tunnel:

```sh
cloudflared tunnel --url http://localhost:8080
```

Copy its HTTPS `trycloudflare.com` URL. Quick Tunnels are temporary: the hostname changes when restarted, and the tunnel must remain running for the demo. For a stable demo hostname, use a dedicated tunnel host you control. GitHub's wildcard callback matching allows subpaths and subdomains beneath the registered callback base and has security implications; use a dedicated controlled host for this app.

The tunnel and Traefik can be running before the management app exists; leave both terminals open while finishing configuration. Do not apply the management Deployment yet. This lets the OAuth callback host be known before creating the GitHub OAuth App and starting the app that requires its credentials.

Create a GitHub OAuth App for this demo. Set its callback URL to the HTTPS origin root:

```text
https://YOUR-TUNNEL-HOST/
```

Enable callback wildcard matching. The root callback URL is required because management redirects to `/auth/callback` and each worker uses a callback under `/projects/{project-id}/auth/callback`; GitHub's matching rule permits callback paths below the configured root. This broad path match is why the host must be dedicated to this app and under your control. Set the application homepage to the same HTTPS origin. Configure the OAuth app only after the tunnel host is known.

Create two strong, independent signing keys and the OAuth Secret in the `tribal` namespace. Enter actual values in a local terminal; do not save them in the repository or shell history. `read -rsp` avoids echoing them:

```sh
read -rp 'GitHub OAuth client ID: ' GITHUB_CLIENT_ID
read -rsp 'GitHub OAuth client secret: ' GITHUB_CLIENT_SECRET; echo
read -rsp 'Management token signing key: ' TOKEN_SIGNING_KEY; echo
read -rsp 'Management session signing key: ' SESSION_SIGNING_KEY; echo
kubectl -n tribal create secret generic tribal-github-oauth \
  --from-literal=GITHUB_CLIENT_ID="$GITHUB_CLIENT_ID" \
  --from-literal=GITHUB_CLIENT_SECRET="$GITHUB_CLIENT_SECRET"
kubectl -n tribal create secret generic tribal-management-auth \
  --from-literal=TOKEN_SIGNING_KEY="$TOKEN_SIGNING_KEY" \
  --from-literal=SESSION_SIGNING_KEY="$SESSION_SIGNING_KEY"
unset GITHUB_CLIENT_ID GITHUB_CLIENT_SECRET TOKEN_SIGNING_KEY SESSION_SIGNING_KEY
```

Update only the `PUBLIC_BASE_URL` value in `k8s/configmaps/management.yaml` to the HTTPS tunnel origin. The other values are fixed for this demo: `DATABASE_PATH=/data/tribal.sqlite3`, `WORKER_IMAGE=tribal-mcp-demo:local`, and `K8S_TEMPLATE_ROOT=/app/k8s`. Once both Secrets exist and the URL is set, apply the management resources and start the app:

```sh
kubectl apply -f k8s/configmaps/management.yaml
kubectl apply -f k8s/deployments/management.yaml
kubectl apply -f k8s/services/management.yaml
kubectl apply -f k8s/ingresses/management.yaml
kubectl -n tribal rollout status deployment/tribal-management
kubectl -n tribal get pods
```

Management startup requires configured OAuth client credentials, signing secrets, worker image, and template root; GitHub credential validity is exercised when a user signs in. It does not report ready with an unhealthy SQLite database. If the Quick Tunnel hostname changes, update the ConfigMap and GitHub app callback settings, restart management, and recreate demo projects so their MCP URLs use the current origin.

## Create a project

Open the tunnel origin in a browser and choose **Sign in with GitHub**. Create a project. The creator's numeric GitHub account ID is its initial only allowed ID. Wait for status `ready`; an error remains visible on the management page if provisioning fails. Create another project if you want to demonstrate two independent workers.

## Connect Codex

Copy the project's MCP URL from the page, then run:

```sh
codex mcp add tribal-project --url 'https://YOUR-TUNNEL-HOST/projects/PROJECT-UUID/mcp'
codex mcp login tribal-project
```

Finish the GitHub authorization in the browser. In Codex, call `get_project_context`. The response contains the project ID and name, `sample: true`, and sample text. To inspect the server configuration, run `codex mcp list`.

Only GitHub IDs in that project's membership list can call its tools. A user outside the list is denied. Worker tokens and project paths are scoped to their project.

## Limits and cleanup

The demo uses stateless Streamable HTTP JSON responses; Quick Tunnels do not support Server-Sent Events, which this demo does not use. KinD's default network plugin may not enforce the included NetworkPolicies, so those manifests do not prove network isolation. There is no enterprise SAML enforcement, invitation or role system, or real graph/knowledge-base integration.

Remove the Codex entry and stop `cloudflared` and `kubectl port-forward`. Remove the cluster when finished:

```sh
kind delete cluster
```

For a project-only reset while keeping the cluster, delete its project resources by label:

```sh
kubectl -n tribal delete all,configmap,secret,ingress -l tribal.dev/project-id=PROJECT-UUID
```
