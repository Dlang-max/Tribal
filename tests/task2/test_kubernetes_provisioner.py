from types import SimpleNamespace

import pytest
import yaml

from tribal.kubernetes_provisioner import KubernetesProvisioner, TEMPLATE_FILES


class KubernetesApiError(Exception):
    def __init__(self, status):
        super().__init__(f"Kubernetes API returned {status}")
        self.status = status


class FakeKubernetesApi:
    def __init__(
        self,
        *,
        generation=1,
        observed_generation=1,
        replicas=1,
        updated_replicas=1,
        ready_replicas=1,
        available_replicas=1,
    ):
        self.resources = {}
        self.create_calls = []
        self.patch_calls = []
        self.generation = generation
        self.observed_generation = observed_generation
        self.replicas = replicas
        self.updated_replicas = updated_replicas
        self.ready_replicas = ready_replicas
        self.available_replicas = available_replicas

    def _create(self, kind, *, namespace, body):
        name = body["metadata"]["name"]
        key = (kind, namespace, name)
        if key in self.resources:
            raise KubernetesApiError(409)
        self.resources[key] = body
        self.create_calls.append(key)

    def _patch(self, kind, *, name, namespace, body):
        key = (kind, namespace, name)
        self.resources[key] = body
        self.patch_calls.append(key)

    def create_namespaced_deployment(self, **kwargs):
        self._create("Deployment", **kwargs)

    def patch_namespaced_deployment(self, **kwargs):
        self._patch("Deployment", **kwargs)

    def create_namespaced_service(self, **kwargs):
        self._create("Service", **kwargs)

    def patch_namespaced_service(self, **kwargs):
        self._patch("Service", **kwargs)

    def create_namespaced_config_map(self, **kwargs):
        self._create("ConfigMap", **kwargs)

    def patch_namespaced_config_map(self, **kwargs):
        self._patch("ConfigMap", **kwargs)

    def create_namespaced_secret(self, **kwargs):
        self._create("Secret", **kwargs)

    def patch_namespaced_secret(self, **kwargs):
        self._patch("Secret", **kwargs)

    def create_namespaced_ingress(self, **kwargs):
        self._create("Ingress", **kwargs)

    def patch_namespaced_ingress(self, **kwargs):
        self._patch("Ingress", **kwargs)

    def read_namespaced_deployment(self, name, namespace):
        key = ("Deployment", namespace, name)
        if key not in self.resources:
            raise KubernetesApiError(404)
        return SimpleNamespace(
            metadata=SimpleNamespace(generation=self.generation),
            spec=SimpleNamespace(replicas=self.replicas),
            status=SimpleNamespace(
                observed_generation=self.observed_generation,
                replicas=self.replicas,
                updated_replicas=self.updated_replicas,
                ready_replicas=self.ready_replicas,
                available_replicas=self.available_replicas,
            ),
        )

    def add_deployment(self, project_id, namespace="tribal"):
        name = f"tribal-project-{project_id}"
        self.resources[("Deployment", namespace, name)] = {"metadata": {"name": name}}


def write_project_templates(root, *, project_name="${PROJECT_NAME}"):
    for relative_path in TEMPLATE_FILES:
        resource_kind = {
            "deployments/": "Deployment",
            "services/": "Service",
            "configmaps/": "ConfigMap",
            "secrets/": "Secret",
            "ingresses/": "Ingress",
        }[relative_path.split("project-worker")[0]]
        name = "tribal-project-${PROJECT_ID}" if resource_kind == "Deployment" else f"tribal-{resource_kind.lower()}-${{PROJECT_ID}}"
        manifest = {
            "apiVersion": "apps/v1" if resource_kind == "Deployment" else "v1",
            "kind": resource_kind,
            "metadata": {"name": name},
        }
        if resource_kind == "ConfigMap":
            manifest["data"] = {"project-name": project_name}
        path = root / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(yaml.safe_dump(manifest), encoding="utf-8")


def make_provisioner(tmp_path, apps, core, networking):
    write_project_templates(tmp_path)
    return KubernetesProvisioner(
        apps,
        core,
        networking,
        worker_image="tribal-worker:local",
        public_base_url="https://tribal.example",
        template_root=tmp_path,
        namespace="tribal-test",
        readiness_timeout=0.1,
        poll_interval=0.001,
    )


def test_provisioner_retries_existing_resources_with_patch_and_waits_for_readiness(tmp_path):
    apps = FakeKubernetesApi()
    core = FakeKubernetesApi()
    networking = FakeKubernetesApi()
    provisioner = make_provisioner(tmp_path, apps, core, networking)
    arguments = ("project-123", "Build notes", frozenset({42}), "signing-key")

    provisioner.provision(*arguments)
    provisioner.provision(*arguments)

    assert len(apps.create_calls) == 1
    assert len(apps.patch_calls) == 1
    assert len(core.create_calls) == 3
    assert len(core.patch_calls) == 3
    assert len(networking.create_calls) == 1
    assert len(networking.patch_calls) == 1
    deployment = apps.resources[("Deployment", "tribal-test", "tribal-project-project-123")]
    assert deployment["metadata"]["labels"]["tribal.dev/project-id"] == "project-123"
    assert provisioner.is_ready("project-123") is True


def test_project_values_remain_yaml_scalar_data_after_rendering(tmp_path):
    write_project_templates(tmp_path)
    apps = FakeKubernetesApi()
    provisioner = KubernetesProvisioner(
        apps,
        FakeKubernetesApi(),
        FakeKubernetesApi(),
        worker_image="tribal-worker:local",
        public_base_url="https://tribal.example",
        template_root=tmp_path,
    )
    injected_name = "literal ${TOKEN_SIGNING_KEY}\nkind: Secret\nmetadata:\n  name: injected"

    resources = provisioner.render_resources("project-1", injected_name, frozenset({42}), "key")

    config = next(resource for resource in resources if resource["kind"] == "ConfigMap")
    assert config["data"]["project-name"] == injected_name
    assert len(resources) == 5


def test_renderer_rejects_unrecognized_template_markers(tmp_path):
    write_project_templates(tmp_path, project_name="${UNKNOWN_MARKER}")
    provisioner = KubernetesProvisioner(
        FakeKubernetesApi(),
        FakeKubernetesApi(),
        FakeKubernetesApi(),
        worker_image="tribal-worker:local",
        public_base_url="https://tribal.example",
        template_root=tmp_path,
        readiness_timeout=0.1,
        poll_interval=0.001,
    )

    with pytest.raises(ValueError, match="Unsupported template marker"):
        provisioner.render_resources("project-1", "valid", frozenset({42}), "key")


def test_provisioning_fails_when_worker_never_becomes_ready(tmp_path):
    apps = FakeKubernetesApi(available_replicas=0)
    provisioner = make_provisioner(tmp_path, apps, FakeKubernetesApi(), FakeKubernetesApi())

    with pytest.raises(TimeoutError, match="did not become ready"):
        provisioner.provision("project-1", "Unready", frozenset({42}), "key")


def test_readiness_rejects_available_replicas_from_an_old_deployment_generation():
    apps = FakeKubernetesApi(
        generation=2,
        observed_generation=1,
        replicas=1,
        updated_replicas=0,
        ready_replicas=1,
        available_replicas=1,
    )
    apps.add_deployment("project-1")
    provisioner = KubernetesProvisioner(
        apps,
        FakeKubernetesApi(),
        FakeKubernetesApi(),
        worker_image="tribal-worker:local",
        public_base_url="https://tribal.example",
    )

    assert provisioner.is_ready("project-1") is False

    apps.observed_generation = 2
    assert provisioner.is_ready("project-1") is False

    apps.updated_replicas = 1
    assert provisioner.is_ready("project-1") is True
