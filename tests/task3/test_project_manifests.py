from collections import Counter
from pathlib import Path

import pytest
import yaml
from kubernetes import client

from tribal.kubernetes_provisioner import KubernetesProvisioner, TEMPLATE_FILES

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
PROJECT_ID = "9f7c2e4a-0648-4a96-8c13-f5d69a3a2f10"


def make_provisioner(*, template_root=None):
    return KubernetesProvisioner(
        apps_api=object(),
        core_api=object(),
        networking_api=object(),
        worker_image="tribal-worker:test",
        public_base_url="https://tribal.example",
        template_root=template_root or REPOSITORY_ROOT / "k8s",
        namespace="tribal",
    )


def resources_by_kind(resources):
    return {resource["kind"]: resource for resource in resources}


def deserialize(resource, model_name):
    """Use the installed Kubernetes client's typed model to catch invalid object shapes."""
    api_client = client.ApiClient()
    return api_client._ApiClient__deserialize(resource, model_name)


def test_renderer_loads_all_five_project_templates_as_typed_kubernetes_objects():
    provisioner = make_provisioner()

    resources = provisioner.render_resources(
        PROJECT_ID,
        "Data platform",
        frozenset({42, 7}),
        "worker-signing-key",
    )

    assert Counter(resource["kind"] for resource in resources) == {
        "Deployment": 1,
        "Service": 1,
        "ConfigMap": 1,
        "Secret": 1,
        "Ingress": 1,
    }
    assert len(TEMPLATE_FILES) == 5
    assert all((REPOSITORY_ROOT / "k8s" / path).is_file() for path in TEMPLATE_FILES)

    resources = resources_by_kind(resources)
    deployment = deserialize(resources["Deployment"], "V1Deployment")
    service = deserialize(resources["Service"], "V1Service")
    configmap = deserialize(resources["ConfigMap"], "V1ConfigMap")
    secret = deserialize(resources["Secret"], "V1Secret")
    ingress = deserialize(resources["Ingress"], "V1Ingress")

    assert deployment.metadata.namespace == "tribal"
    assert service.metadata.namespace == configmap.metadata.namespace == secret.metadata.namespace == "tribal"
    assert ingress.metadata.namespace == "tribal"
    assert deployment.spec.replicas == 1
    assert deployment.spec.template.spec.service_account_name == "tribal-project-worker"
    assert deployment.spec.template.spec.automount_service_account_token is False
    container = deployment.spec.template.spec.containers[0]
    assert container.image == "tribal-worker:test"
    assert any(port.container_port == 8000 for port in container.ports)
    assert container.startup_probe.http_get.path == "/healthz"
    assert container.liveness_probe.http_get.path == "/healthz"
    assert container.readiness_probe.http_get.path == "/readyz"
    assert any(port.port == 8000 and port.target_port == "http" for port in service.spec.ports)


def test_worker_environment_references_project_config_and_shared_github_secret():
    resources = resources_by_kind(
        make_provisioner().render_resources(
            PROJECT_ID,
            "Data platform",
            frozenset({42, 7}),
            "worker-signing-key",
        )
    )
    deployment = resources["Deployment"]
    pod = deployment["spec"]["template"]["spec"]
    container = pod["containers"][0]
    env = {entry["name"]: entry for entry in container.get("env", [])}
    configmap = resources["ConfigMap"]
    assert any(
        entry.get("configMapRef", {}).get("name") == configmap["metadata"]["name"]
        for entry in container.get("envFrom", [])
    )
    effective_env = dict(configmap["data"])
    effective_env.update({
        name: entry.get("value")
        for name, entry in env.items()
        if "value" in entry
    })

    assert {
        "PROJECT_ID",
        "PROJECT_NAME",
        "ALLOWED_GITHUB_IDS",
        "PUBLIC_BASE_URL",
        "TOKEN_SIGNING_KEY",
        "GITHUB_CLIENT_ID",
        "GITHUB_CLIENT_SECRET",
    } <= (effective_env.keys() | env.keys())
    assert effective_env["PROJECT_ID"] == PROJECT_ID
    assert effective_env["PROJECT_NAME"] == "Data platform"
    assert effective_env["ALLOWED_GITHUB_IDS"] == "7,42"
    assert effective_env["PUBLIC_BASE_URL"] == "https://tribal.example"
    assert env["TOKEN_SIGNING_KEY"]["valueFrom"]["secretKeyRef"]["name"] == resources["Secret"]["metadata"]["name"]
    assert env["GITHUB_CLIENT_ID"]["valueFrom"]["secretKeyRef"]["name"] != resources["Secret"]["metadata"]["name"]
    assert env["GITHUB_CLIENT_SECRET"]["valueFrom"]["secretKeyRef"]["name"] == env["GITHUB_CLIENT_ID"]["valueFrom"]["secretKeyRef"]["name"]


def test_ingress_preserves_mcp_prefix_and_both_oauth_discovery_paths():
    resources = resources_by_kind(
        make_provisioner().render_resources(
            PROJECT_ID,
            "Data platform",
            frozenset({42}),
            "worker-signing-key",
        )
    )
    ingress = deserialize(resources["Ingress"], "V1Ingress")
    paths = ingress.spec.rules[0].http.paths
    by_path = {item.path: item for item in paths}

    assert set(by_path) == {
        f"/projects/{PROJECT_ID}",
        f"/.well-known/oauth-authorization-server/projects/{PROJECT_ID}",
        f"/.well-known/oauth-protected-resource/projects/{PROJECT_ID}/mcp",
    }
    assert all(item.path_type == "Prefix" for item in paths)
    assert all(item.backend.service.port.number == 8000 for item in paths)
    assert all(item.backend.service.name == resources["Service"]["metadata"]["name"] for item in paths)
    annotations = ingress.metadata.annotations or {}
    assert not any("rewrite" in key.lower() for key in annotations)


def test_project_id_and_name_newlines_stay_scalar_data_when_rendered():
    hostile_name = 'notes\nkind: Secret\nmetadata:\n  name: injected\n${WORKER_IMAGE}'

    resources = make_provisioner().render_resources(
        PROJECT_ID,
        hostile_name,
        frozenset({42}),
        "signing-key",
    )

    assert len(resources) == 5
    assert Counter(resource["kind"] for resource in resources) == {
        "Deployment": 1,
        "Service": 1,
        "ConfigMap": 1,
        "Secret": 1,
        "Ingress": 1,
    }
    rendered_config = next(resource for resource in resources if resource["kind"] == "ConfigMap")
    assert rendered_config["data"]["PROJECT_ID"] == PROJECT_ID
    assert deserialize(rendered_config, "V1ConfigMap").data["PROJECT_NAME"] == hostile_name
    assert all(resource["kind"] != "ClusterRole" for resource in resources)


@pytest.mark.parametrize("template_path", TEMPLATE_FILES)
def test_renderer_fails_clearly_if_a_required_project_template_is_missing(tmp_path, template_path):
    for path in TEMPLATE_FILES:
        if path == template_path:
            continue
        kind = {
            "deployments/": "Deployment",
            "services/": "Service",
            "configmaps/": "ConfigMap",
            "secrets/": "Secret",
            "ingresses/": "Ingress",
        }[path.split("project-worker")[0]]
        api_version = "apps/v1" if kind == "Deployment" else (
            "networking.k8s.io/v1" if kind == "Ingress" else "v1"
        )
        manifest = {
            "apiVersion": api_version,
            "kind": kind,
            "metadata": {"name": "fixture-${PROJECT_ID}"},
        }
        target = tmp_path / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(yaml.safe_dump(manifest), encoding="utf-8")

    with pytest.raises(FileNotFoundError, match="Required Kubernetes project template"):
        make_provisioner(template_root=tmp_path).render_resources(
            PROJECT_ID,
            "Data platform",
            frozenset({42}),
            "worker-signing-key",
        )
