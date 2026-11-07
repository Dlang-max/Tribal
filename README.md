# Tribal

Tribal's current runnable demo is a GitHub-authenticated project manager that provisions one stateless MCP worker per project on a local KinD cluster. Each worker exposes an explicitly labeled sample-context tool. This is a local hackathon demo, not the complete remote knowledge base described in the broader architecture.

See [Connect Codex to Tribal](docs/connecting-codex-to-tribal.md) for the KinD, GitHub OAuth, tunnel, and Codex walkthrough. The approved implementation plan and task reports are in [`docs/superpowers/plans/`](docs/superpowers/plans/).

## Runtime

- Python 3.12, FastAPI, FastMCP, Authlib, SQLite, and the Kubernetes Python client.
- `python -m tribal management` starts the browser management app on `0.0.0.0:8000` (or `PORT`).
- `python -m tribal worker` starts a configured project MCP worker on the same address and port.
- The shared image is built from `docker/Dockerfile`; Kubernetes resources are under `k8s/`.

Management requires `PUBLIC_BASE_URL`, `GITHUB_CLIENT_ID`, `GITHUB_CLIENT_SECRET`, `TOKEN_SIGNING_KEY`, `SESSION_SIGNING_KEY`, `DATABASE_PATH`, `WORKER_IMAGE`, and `K8S_TEMPLATE_ROOT`. Missing settings stop startup. The KinD walkthrough supplies these via uncommitted Kubernetes Secrets and a ConfigMap.

The project uses no checked-in live credentials. Do not commit populated Secret manifests, environment files, tokens, or signing keys.
