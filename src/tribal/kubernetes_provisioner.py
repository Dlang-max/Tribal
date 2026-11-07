"""Idempotent renderer and Kubernetes provisioner for one worker per project."""

from __future__ import annotations

import copy
import os
import re
import time
from collections import Counter
from pathlib import Path
from typing import Any

import yaml

TEMPLATE_FILES = (
    "deployments/project-worker.yaml.template",
    "services/project-worker.yaml.template",
    "configmaps/project-worker.yaml.template",
    "secrets/project-worker.yaml.template",
    "ingresses/project-worker.yaml.template",
)
_ALLOWED_KINDS = {"Deployment", "Service", "ConfigMap", "Secret", "Ingress"}
_MARKER_PATTERN = re.compile(r"\$\{([^{}]+)\}")


class KubernetesProvisioner:
    """Apply the fixed Tribal worker templates and wait for Deployment readiness."""

    def __init__(
        self,
        apps_api: Any,
        core_api: Any,
        networking_api: Any,
        *,
        worker_image: str,
        public_base_url: str,
        template_root: str | Path | None = None,
        namespace: str = "tribal",
        readiness_timeout: float = 90,
        poll_interval: float = 2,
    ) -> None:
        self.apps_api = apps_api
        self.core_api = core_api
        self.networking_api = networking_api
        self.worker_image = worker_image.strip()
        self.public_base_url = public_base_url.rstrip("/")
        self.template_root = Path(template_root) if template_root else Path(__file__).resolve().parents[2] / "k8s"
        self.namespace = namespace
        self.readiness_timeout = readiness_timeout
        self.poll_interval = poll_interval
        if not self.worker_image:
            raise ValueError("WORKER_IMAGE must be configured")

    @classmethod
    def from_cluster(
        cls,
        *,
        public_base_url: str,
        worker_image: str | None = None,
        template_root: str | Path | None = None,
        namespace: str = "tribal",
        readiness_timeout: float = 90,
        poll_interval: float = 2,
    ) -> "KubernetesProvisioner":
        """Load in-cluster or kubeconfig credentials and create typed Kubernetes clients."""
        from kubernetes import client, config

        try:
            config.load_incluster_config()
        except config.ConfigException:
            config.load_kube_config()
        return cls(
            client.AppsV1Api(),
            client.CoreV1Api(),
            client.NetworkingV1Api(),
            worker_image=worker_image or os.environ.get("WORKER_IMAGE", ""),
            public_base_url=public_base_url,
            template_root=template_root,
            namespace=namespace,
            readiness_timeout=readiness_timeout,
            poll_interval=poll_interval,
        )

    def render_resources(
        self,
        project_id: str,
        project_name: str,
        allowed_github_ids: frozenset[int],
        token_signing_key: str,
    ) -> list[dict[str, Any]]:
        """Parse only the five approved project templates and replace scalar markers."""
        values = {
            "PROJECT_ID": project_id,
            "PROJECT_NAME": project_name,
            "PUBLIC_BASE_URL": self.public_base_url,
            "ALLOWED_GITHUB_IDS": ",".join(str(value) for value in sorted(allowed_github_ids)),
            "TOKEN_SIGNING_KEY": token_signing_key,
            "WORKER_IMAGE": self.worker_image,
        }
        resources: list[dict[str, Any]] = []
        for relative_path in TEMPLATE_FILES:
            path = self.template_root / relative_path
            if not path.is_file():
                raise FileNotFoundError(f"Required Kubernetes project template is missing: {relative_path}")
            documents = list(yaml.safe_load_all(path.read_text(encoding="utf-8")))
            for resource in documents:
                if not isinstance(resource, dict) or resource.get("kind") not in _ALLOWED_KINDS:
                    raise ValueError(f"Unsupported resource in project template: {relative_path}")
                rendered = self._replace_markers(copy.deepcopy(resource), values)
                metadata = rendered.setdefault("metadata", {})
                metadata["namespace"] = self.namespace
                labels = metadata.setdefault("labels", {})
                labels["app.kubernetes.io/managed-by"] = "tribal"
                labels["tribal.dev/project-id"] = project_id
                resources.append(rendered)
        expected = {kind: 1 for kind in _ALLOWED_KINDS}
        actual = Counter(resource["kind"] for resource in resources)
        if actual != expected:
            raise ValueError(
                "Project templates must define exactly one Deployment, Service, ConfigMap, Secret, "
                f"and Ingress; found {dict(actual)}"
            )
        return resources

    @classmethod
    def _replace_markers(cls, value: Any, replacements: dict[str, str]) -> Any:
        if isinstance(value, dict):
            return {
                cls._replace_string(key, replacements) if isinstance(key, str) else key:
                cls._replace_markers(child, replacements)
                for key, child in value.items()
            }
        elif isinstance(value, list):
            return [cls._replace_markers(child, replacements) for child in value]
        elif isinstance(value, str):
            return cls._replace_string(value, replacements)
        return value

    @staticmethod
    def _replace_string(value: str, replacements: dict[str, str]) -> str:
        markers = list(_MARKER_PATTERN.finditer(value))
        if value.count("${") != len(markers):
            raise ValueError("Malformed template marker")
        for marker in markers:
            if marker.group(1) not in replacements:
                raise ValueError(f"Unsupported template marker: {marker.group(0)}")
        # Substitute only markers present in the source scalar. Replacement data is
        # never processed again, so user text resembling another marker stays inert.
        return _MARKER_PATTERN.sub(lambda match: replacements[match.group(1)], value)

    def provision(
        self,
        project_id: str,
        name: str,
        allowed_github_ids: frozenset[int],
        token_signing_key: str,
    ) -> None:
        resources = self.render_resources(project_id, name, allowed_github_ids, token_signing_key)
        for resource in resources:
            self._upsert(resource)
        deadline = time.monotonic() + self.readiness_timeout
        while time.monotonic() < deadline:
            if self.is_ready(project_id):
                return
            time.sleep(self.poll_interval)
        raise TimeoutError(f"Worker deployment for project {project_id} did not become ready in time")

    def is_ready(self, project_id: str) -> bool:
        deployment_name = f"tribal-project-{project_id}"
        try:
            deployment = self.apps_api.read_namespaced_deployment(deployment_name, self.namespace)
        except Exception as exc:
            if getattr(exc, "status", None) == 404:
                return False
            raise
        metadata = getattr(deployment, "metadata", None)
        spec = getattr(deployment, "spec", None)
        deployment_status = getattr(deployment, "status", None)
        generation = getattr(metadata, "generation", None)
        observed_generation = getattr(deployment_status, "observed_generation", None)
        desired_replicas = getattr(spec, "replicas", 1)
        if desired_replicas is None:
            desired_replicas = 1
        if (
            not isinstance(generation, int)
            or not isinstance(observed_generation, int)
            or observed_generation < generation
            or desired_replicas < 1
        ):
            return False

        # availableReplicas can include Pods from the prior ReplicaSet. Require
        # the controller to observe this generation and finish the rollout before
        # reporting ready; replicas == desired also excludes lingering old Pods.
        replicas = getattr(deployment_status, "replicas", 0) or 0
        updated = getattr(deployment_status, "updated_replicas", 0) or 0
        ready = getattr(deployment_status, "ready_replicas", 0) or 0
        available = getattr(deployment_status, "available_replicas", 0) or 0
        return (
            replicas == desired_replicas
            and updated == desired_replicas
            and ready >= desired_replicas
            and available >= desired_replicas
        )

    def _upsert(self, resource: dict[str, Any]) -> None:
        kind = resource["kind"]
        name = resource["metadata"]["name"]
        namespace = self.namespace
        if kind == "Deployment":
            api, create, patch = self.apps_api, "create_namespaced_deployment", "patch_namespaced_deployment"
        elif kind == "Service":
            api, create, patch = self.core_api, "create_namespaced_service", "patch_namespaced_service"
        elif kind == "ConfigMap":
            api, create, patch = self.core_api, "create_namespaced_config_map", "patch_namespaced_config_map"
        elif kind == "Secret":
            api, create, patch = self.core_api, "create_namespaced_secret", "patch_namespaced_secret"
        else:
            api, create, patch = (
                self.networking_api,
                "create_namespaced_ingress",
                "patch_namespaced_ingress",
            )
        method_create = getattr(api, create)
        method_patch = getattr(api, patch)
        try:
            method_create(namespace=namespace, body=resource)
        except Exception as exc:
            if getattr(exc, "status", None) != 409:
                raise
            method_patch(name=name, namespace=namespace, body=resource)
