from pathlib import Path
import re

import yaml
from kubernetes import client

from tribal.kubernetes_provisioner import KubernetesProvisioner

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
K8S_ROOT = REPOSITORY_ROOT / "k8s"
EXPECTED_K8S_DIRECTORIES = {
    "configmaps",
    "deployments",
    "ingresses",
    "namespaces",
    "network-policies",
    "persistent-volume-claims",
    "rbac",
    "secrets",
    "service-accounts",
    "services",
}


def load_document(relative_path):
    return yaml.safe_load((K8S_ROOT / relative_path).read_text(encoding="utf-8"))


def load_documents(folder):
    documents = []
    for path in sorted((K8S_ROOT / folder).glob("*.yaml")):
        documents.extend(yaml.safe_load_all(path.read_text(encoding="utf-8")))
    return [document for document in documents if document]


def deserialize(resource, model_name):
    api_client = client.ApiClient()
    return api_client._ApiClient__deserialize(resource, model_name)


def normalized_rules(role):
    return {
        (
            tuple(sorted(rule.get("apiGroups", []))),
            tuple(sorted(rule.get("resources", []))),
            tuple(sorted(rule.get("verbs", []))),
        )
        for rule in role["rules"]
    }


def test_required_kind_resource_folders_are_present():
    actual_directories = {path.name for path in K8S_ROOT.iterdir() if path.is_dir()}

    assert EXPECTED_K8S_DIRECTORIES <= actual_directories


def test_management_role_grants_exact_provisioner_api_operations():
    role = load_document("rbac/management-role.yaml")
    binding = load_document("rbac/management-rolebinding.yaml")

    deserialize(role, "V1Role")
    deserialize(binding, "V1RoleBinding")
    assert role["metadata"]["namespace"] == "tribal"
    assert binding["metadata"]["namespace"] == "tribal"
    assert binding["roleRef"] == {
        "apiGroup": "rbac.authorization.k8s.io",
        "kind": "Role",
        "name": role["metadata"]["name"],
    }
    assert binding["subjects"] == [{
        "kind": "ServiceAccount",
        "name": "tribal-management",
        "namespace": "tribal",
    }]
    assert normalized_rules(role) == {
        (("apps",), ("deployments",), ("create", "get", "patch")),
        (("",), ("configmaps", "secrets", "services"), ("create", "patch")),
        (("networking.k8s.io",), ("ingresses",), ("create", "patch")),
    }


def test_traefik_routing_permissions_are_namespaced_and_limited_to_routing():
    role = load_document("rbac/traefik-role.yaml")
    binding = load_document("rbac/traefik-rolebinding.yaml")

    deserialize(role, "V1Role")
    deserialize(binding, "V1RoleBinding")
    assert role["metadata"]["namespace"] == binding["metadata"]["namespace"] == "tribal"
    assert binding["roleRef"]["kind"] == "Role"
    assert binding["roleRef"]["name"] == role["metadata"]["name"]
    assert binding["subjects"] == [{
        "kind": "ServiceAccount",
        "name": "traefik",
        "namespace": "tribal",
    }]
    assert normalized_rules(role) == {
        (("",), ("endpoints", "secrets", "services"), ("get", "list", "watch")),
        (("discovery.k8s.io",), ("endpointslices",), ("get", "list", "watch")),
        (("networking.k8s.io",), ("ingresses",), ("get", "list", "watch")),
        (("networking.k8s.io",), ("ingresses/status",), ("get", "patch", "update")),
    }


def test_all_supplied_rbac_is_namespaced_and_worker_service_account_is_unbound():
    rbac_documents = load_documents("rbac")
    assert rbac_documents
    assert all(document["kind"] in {"Role", "RoleBinding"} for document in rbac_documents)
    assert all(document["metadata"].get("namespace") == "tribal" for document in rbac_documents)

    worker_account = load_document("service-accounts/project-worker.yaml")
    deployment_template = (K8S_ROOT / "deployments/project-worker.yaml.template").read_text(encoding="utf-8")
    assert worker_account["automountServiceAccountToken"] is False
    assert "serviceAccountName: tribal-project-worker" in deployment_template
    assert "automountServiceAccountToken: false" in deployment_template
    worker_name = worker_account["metadata"]["name"]
    assert not any(
        subject.get("kind") == "ServiceAccount" and subject.get("name") == worker_name
        for binding in rbac_documents
        if binding["kind"] == "RoleBinding"
        for subject in binding.get("subjects", [])
    )


def test_network_policies_select_application_pods_allow_traefik_and_document_limits():
    management_policy = load_document("network-policies/management.yaml")
    worker_policy = load_document("network-policies/project-workers.yaml")
    management = deserialize(management_policy, "V1NetworkPolicy")
    workers = deserialize(worker_policy, "V1NetworkPolicy")

    assert management.spec.pod_selector.match_labels == {
        "app.kubernetes.io/name": "tribal-management"
    }
    assert workers.spec.pod_selector.match_labels == {
        "app.kubernetes.io/name": "tribal-project-worker"
    }
    for policy in (management, workers):
        assert {"Ingress", "Egress"} == set(policy.spec.policy_types)
        ingress = policy.spec.ingress[0]
        assert ingress.var_from[0].pod_selector.match_labels == {
            "app.kubernetes.io/name": "traefik"
        }
        assert any(port.port == 8000 and port.protocol == "TCP" for port in ingress.ports)
        egress_ports = {
            (port.port, port.protocol)
            for rule in policy.spec.egress
            for port in rule.ports
        }
        assert {(53, "UDP"), (53, "TCP"), (443, "TCP")} <= egress_ports

    for path in (K8S_ROOT / "network-policies").glob("*.yaml"):
        notes = path.read_text(encoding="utf-8").lower()
        assert "kind" in notes and "cni" in notes and "not enforce" in notes
        assert "github" in notes and "dns" in notes and "443" in notes



def test_static_kubernetes_objects_deserialize_against_installed_api_models():
    models = {
        "ConfigMap": "V1ConfigMap",
        "Deployment": "V1Deployment",
        "Ingress": "V1Ingress",
        "Namespace": "V1Namespace",
        "NetworkPolicy": "V1NetworkPolicy",
        "PersistentVolumeClaim": "V1PersistentVolumeClaim",
        "Role": "V1Role",
        "RoleBinding": "V1RoleBinding",
        "Secret": "V1Secret",
        "Service": "V1Service",
        "ServiceAccount": "V1ServiceAccount",
    }
    documents = [
        document
        for directory in EXPECTED_K8S_DIRECTORIES
        for document in load_documents(directory)
    ]

    assert documents
    for document in documents:
        assert document["apiVersion"]
        assert document["kind"] in models
        deserialize(document, models[document["kind"]])
        if document["kind"] != "Namespace":
            assert document["metadata"].get("namespace") == "tribal"


def test_secret_examples_contain_only_empty_configuration_placeholders():
    sensitive_keys = {
        "GITHUB_CLIENT_ID",
        "GITHUB_CLIENT_SECRET",
        "TOKEN_SIGNING_KEY",
        "SESSION_SIGNING_KEY",
    }
    seen_keys = set()
    for secret in load_documents("secrets"):
        for key in sensitive_keys & secret.get("stringData", {}).keys():
            seen_keys.add(key)
            assert secret["stringData"][key] == ""

    assert seen_keys == sensitive_keys


def test_docker_image_build_context_contains_runtime_and_kubernetes_templates():
    dockerfile = (REPOSITORY_ROOT / "docker/Dockerfile").read_text(encoding="utf-8")
    dockerignore = (REPOSITORY_ROOT / "docker/Dockerfile.dockerignore").read_text(encoding="utf-8")

    assert "FROM python:3.12-slim" in dockerfile
    assert "COPY requirements.lock" in dockerfile
    assert "COPY pyproject.toml requirements.txt" in dockerfile
    assert "COPY src ./src" in dockerfile
    assert "COPY k8s ./k8s" in dockerfile
    assert "python -m pip install" in dockerfile
    assert "EXPOSE 8000" in dockerfile
    assert "USER 10001:10001" in dockerfile
    assert ".venv" in dockerignore and "tests" in dockerignore

    normalized_dockerfile = dockerfile.replace("\\\n", " ")
    environment = re.search(
        r"ENV\s+HOME=(\S+)\s+FASTMCP_HOME=(\S+)", normalized_dockerfile
    )
    assert environment
    home, fastmcp_home = environment.groups()
    assert home == "/home/tribal"
    assert fastmcp_home == str(Path(home) / ".local/share/fastmcp")

    mkdir_command = f"mkdir -p {fastmcp_home}"
    chown_command = f"chown -R 10001:10001 {home}"
    user_instruction = "USER 10001:10001"
    assert mkdir_command in normalized_dockerfile
    assert chown_command in normalized_dockerfile
    assert normalized_dockerfile.index(mkdir_command) < normalized_dockerfile.index(chown_command)
    assert normalized_dockerfile.index(chown_command) < normalized_dockerfile.index(user_instruction)


def assert_deployment_matches_service(deployment, service):
    labels = deployment["spec"]["template"]["metadata"]["labels"]
    deployment_selector = deployment["spec"]["selector"]["matchLabels"]
    service_selector = service["spec"]["selector"]

    assert all(labels.get(key) == value for key, value in deployment_selector.items())
    assert service_selector
    assert all(labels.get(key) == value for key, value in service_selector.items())
    assert all(service_selector.get(key) == value for key, value in deployment_selector.items())


def assert_service_targets_container_port(service, deployment):
    containers = deployment["spec"]["template"]["spec"].get("containers", [])
    exposed_ports = [port for container in containers for port in container.get("ports", [])]
    assert exposed_ports

    for service_port in service["spec"]["ports"]:
        target_port = service_port.get("targetPort", service_port["port"])
        if isinstance(target_port, int):
            assert any(port.get("containerPort") == target_port for port in exposed_ports)
        else:
            matching_ports = [port for port in exposed_ports if port.get("name") == target_port]
            assert matching_ports
            assert all(isinstance(port.get("containerPort"), int) for port in matching_ports)


def assert_ingress_targets_service_ports(ingress, service):
    service_ports = {
        port["port"]
        for port in service["spec"]["ports"]
    }
    for rule in ingress["spec"].get("rules", []):
        for path in rule.get("http", {}).get("paths", []):
            backend = path["backend"]["service"]
            assert backend["name"] == service["metadata"]["name"]
            assert backend["port"]["number"] in service_ports


def assert_container_references_resolve(container, *, configmaps, secrets):
    configmap_by_name = {item["metadata"]["name"]: item for item in configmaps}
    secret_by_name = {item["metadata"]["name"]: item for item in secrets}

    for source in container.get("envFrom", []):
        configmap_ref = source.get("configMapRef")
        if configmap_ref:
            assert configmap_ref["name"] in configmap_by_name
            assert configmap_by_name[configmap_ref["name"]].get("data")
        secret_ref = source.get("secretRef")
        if secret_ref:
            assert secret_ref["name"] in secret_by_name
            secret = secret_by_name[secret_ref["name"]]
            assert secret.get("stringData") or secret.get("data")

    for env in container.get("env", []):
        value_from = env.get("valueFrom", {})
        secret_key_ref = value_from.get("secretKeyRef")
        if secret_key_ref:
            secret = secret_by_name[secret_key_ref["name"]]
            secret_keys = set(secret.get("stringData", {})) | set(secret.get("data", {}))
            assert secret_key_ref["key"] in secret_keys
        configmap_key_ref = value_from.get("configMapKeyRef")
        if configmap_key_ref:
            configmap = configmap_by_name[configmap_key_ref["name"]]
            assert configmap_key_ref["key"] in configmap.get("data", {})


def unique_resource(resources, description, predicate):
    matching = [resource for resource in resources if predicate(resource)]
    assert len(matching) == 1, f"Expected one {description}, found {len(matching)}"
    return matching[0]


def deployment_with_container(folder, container_name):
    return unique_resource(
        load_documents(folder),
        f"Deployment with {container_name} container",
        lambda item: item.get("kind") == "Deployment"
        and any(
            container.get("name") == container_name
            for container in item["spec"]["template"]["spec"].get("containers", [])
        ),
    )


def service_selecting_deployment(folder, deployment):
    labels = deployment["spec"]["template"]["metadata"]["labels"]
    return unique_resource(
        load_documents(folder),
        f"Service selecting {deployment['metadata']['name']}",
        lambda item: item.get("kind") == "Service"
        and all(labels.get(key) == value for key, value in item["spec"].get("selector", {}).items()),
    )


def test_management_and_traefik_services_select_their_deployment_pods():
    for container_name in ("management", "traefik"):
        deployment = deployment_with_container("deployments", container_name)
        service = service_selecting_deployment("services", deployment)
        assert_deployment_matches_service(deployment, service)
        assert_service_targets_container_port(service, deployment)


def test_management_ingress_routes_to_a_port_exposed_by_its_selected_service():
    deployment = deployment_with_container("deployments", "management")
    service = service_selecting_deployment("services", deployment)
    ingress = unique_resource(
        load_documents("ingresses"),
        "Ingress routing to the management Service",
        lambda item: item.get("kind") == "Ingress"
        and any(
            path.get("backend", {}).get("service", {}).get("name") == service["metadata"]["name"]
            for rule in item.get("spec", {}).get("rules", [])
            for path in rule.get("http", {}).get("paths", [])
        ),
    )

    assert_ingress_targets_service_ports(ingress, service)


def test_traefik_service_port_matches_its_configured_http_entrypoint():
    deployment = deployment_with_container("deployments", "traefik")
    service = service_selecting_deployment("services", deployment)
    assert_service_targets_container_port(service, deployment)
    containers = deployment["spec"]["template"]["spec"]["containers"]
    traefik = next(container for container in containers if container.get("name") == "traefik")
    exposed_web_port = next(
        port["containerPort"]
        for port in traefik.get("ports", [])
        if port.get("name") == "web"
    )
    args = traefik.get("args", [])
    assert f"--entrypoints.web.address=:{exposed_web_port}" in args
    assert any(port.get("port") == 80 and port.get("targetPort") == "web" for port in service["spec"]["ports"])


def test_management_runtime_configmap_has_required_frozen_values():
    deployment = deployment_with_container("deployments", "management")
    container = deployment["spec"]["template"]["spec"]["containers"][0]
    configmap_refs = [
        source["configMapRef"]["name"]
        for source in container.get("envFrom", [])
        if "configMapRef" in source
    ]
    configmap = unique_resource(
        load_documents("configmaps"),
        "ConfigMap referenced by management envFrom",
        lambda item: item.get("kind") == "ConfigMap"
        and item["metadata"]["name"] in configmap_refs,
    )
    data = configmap.get("data", {})

    assert data == {
        "PUBLIC_BASE_URL": "REPLACE_WITH_PUBLIC_HTTPS_URL",
        "DATABASE_PATH": "/data/tribal.sqlite3",
        "WORKER_IMAGE": "tribal-mcp-demo:local",
        "K8S_TEMPLATE_ROOT": "/app/k8s",
    }
    assert all(value for value in data.values())


def test_management_environment_references_configmaps_and_secret_keys_that_exist():
    deployment = deployment_with_container("deployments", "management")
    container = deployment["spec"]["template"]["spec"]["containers"][0]

    assert_container_references_resolve(
        container,
        configmaps=load_documents("configmaps"),
        secrets=load_documents("secrets"),
    )


def test_rendered_project_resources_have_consistent_selector_route_and_secret_wiring():
    resources = KubernetesProvisioner(
        apps_api=object(),
        core_api=object(),
        networking_api=object(),
        worker_image="tribal-worker:test",
        public_base_url="https://tribal.example",
        template_root=K8S_ROOT,
        namespace="tribal",
    ).render_resources(
        "9f7c2e4a-0648-4a96-8c13-f5d69a3a2f10",
        "Data platform",
        frozenset({42}),
        "worker-signing-key",
    )
    resources_by_kind = {resource["kind"]: resource for resource in resources}
    deployment = resources_by_kind["Deployment"]
    service = resources_by_kind["Service"]
    ingress = resources_by_kind["Ingress"]
    configmap = resources_by_kind["ConfigMap"]
    per_project_secret = resources_by_kind["Secret"]

    assert_deployment_matches_service(deployment, service)
    assert_service_targets_container_port(service, deployment)
    assert_ingress_targets_service_ports(ingress, service)
    worker_container = deployment["spec"]["template"]["spec"]["containers"][0]
    assert_container_references_resolve(
        worker_container,
        configmaps=[configmap],
        secrets=[per_project_secret, *load_documents("secrets")],
    )


def test_different_project_worker_services_cannot_select_each_others_pods():
    provisioner = KubernetesProvisioner(
        apps_api=object(),
        core_api=object(),
        networking_api=object(),
        worker_image="tribal-worker:test",
        public_base_url="https://tribal.example",
        template_root=K8S_ROOT,
        namespace="tribal",
    )
    first_id = "9f7c2e4a-0648-4a96-8c13-f5d69a3a2f10"
    second_id = "8b5d0c16-8859-4d90-a33e-dff214479f8e"
    first_resources = {
        resource["kind"]: resource
        for resource in provisioner.render_resources(first_id, "First", frozenset({42}), "key-a")
    }
    second_resources = {
        resource["kind"]: resource
        for resource in provisioner.render_resources(second_id, "Second", frozenset({42}), "key-b")
    }

    first_deployment, first_service = first_resources["Deployment"], first_resources["Service"]
    second_deployment, second_service = second_resources["Deployment"], second_resources["Service"]
    assert_deployment_matches_service(first_deployment, first_service)
    assert_deployment_matches_service(second_deployment, second_service)
    assert_service_targets_container_port(first_service, first_deployment)
    assert_service_targets_container_port(second_service, second_deployment)

    first_selector = first_service["spec"]["selector"]
    second_selector = second_service["spec"]["selector"]
    first_pod_labels = first_deployment["spec"]["template"]["metadata"]["labels"]
    second_pod_labels = second_deployment["spec"]["template"]["metadata"]["labels"]
    project_id_label = "tribal.dev/project-id"
    assert first_selector[project_id_label] == first_id
    assert second_selector[project_id_label] == second_id
    assert first_selector[project_id_label] != second_selector[project_id_label]
    assert all(first_pod_labels.get(key) == value for key, value in first_selector.items())
    assert all(second_pod_labels.get(key) == value for key, value in second_selector.items())
    assert not all(first_pod_labels.get(key) == value for key, value in second_selector.items())
    assert not all(second_pod_labels.get(key) == value for key, value in first_selector.items())
