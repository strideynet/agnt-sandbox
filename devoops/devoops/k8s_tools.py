"""Kubernetes tools for the devoops agent."""

import json
import yaml
from typing import Any
from kubernetes import client, config
from kubernetes.client.rest import ApiException
from kubernetes.dynamic import DynamicClient
from kubernetes.dynamic.exceptions import ResourceNotFoundError


class K8sClient:
    """Wrapper around Kubernetes client with tool methods."""

    def __init__(self, in_cluster: bool = False):
        """Initialize the Kubernetes client.

        Args:
            in_cluster: If True, use in-cluster config. Otherwise use kubeconfig.
        """
        if in_cluster:
            config.load_incluster_config()
        else:
            config.load_kube_config()

        self.core_v1 = client.CoreV1Api()
        self.apps_v1 = client.AppsV1Api()

        # Dynamic client for applying arbitrary manifests
        k8s_client = client.ApiClient()
        self.dynamic_client = DynamicClient(k8s_client)

    def list_pods(self, namespace: str = "default") -> str:
        """List all pods in a namespace.

        Args:
            namespace: The namespace to list pods from

        Returns:
            JSON string with pod information
        """
        try:
            pods = self.core_v1.list_namespaced_pod(namespace=namespace)
            pod_list = []
            for pod in pods.items:
                pod_info = {
                    "name": pod.metadata.name,
                    "namespace": pod.metadata.namespace,
                    "status": pod.status.phase,
                    "restart_count": sum(
                        cs.restart_count for cs in (pod.status.container_statuses or [])
                    ),
                    "containers": [c.name for c in pod.spec.containers],
                }
                pod_list.append(pod_info)
            return json.dumps({"pods": pod_list}, indent=2)
        except ApiException as e:
            return json.dumps({"error": str(e)}, indent=2)

    def get_pod_logs(self, name: str, namespace: str = "default", tail_lines: int = 100) -> str:
        """Get logs from a pod.

        Args:
            name: Pod name
            namespace: Namespace the pod is in
            tail_lines: Number of lines to retrieve from the end of the logs

        Returns:
            Pod logs as a string
        """
        try:
            logs = self.core_v1.read_namespaced_pod_log(
                name=name,
                namespace=namespace,
                tail_lines=tail_lines
            )
            return logs
        except ApiException as e:
            return json.dumps({"error": str(e)}, indent=2)

    def describe_pod(self, name: str, namespace: str = "default") -> str:
        """Get detailed information about a pod.

        Args:
            name: Pod name
            namespace: Namespace the pod is in

        Returns:
            JSON string with detailed pod information
        """
        try:
            pod = self.core_v1.read_namespaced_pod(name=name, namespace=namespace)
            pod_info = {
                "name": pod.metadata.name,
                "namespace": pod.metadata.namespace,
                "status": pod.status.phase,
                "node": pod.spec.node_name,
                "containers": [
                    {
                        "name": c.name,
                        "image": c.image,
                        "status": next(
                            (cs.state for cs in (pod.status.container_statuses or [])
                             if cs.name == c.name),
                            None
                        ),
                    }
                    for c in pod.spec.containers
                ],
                "conditions": [
                    {"type": c.type, "status": c.status, "reason": c.reason}
                    for c in (pod.status.conditions or [])
                ],
                "events": self._get_pod_events(name, namespace),
            }
            return json.dumps(pod_info, indent=2, default=str)
        except ApiException as e:
            return json.dumps({"error": str(e)}, indent=2)

    def _get_pod_events(self, pod_name: str, namespace: str) -> list[dict[str, Any]]:
        """Get events for a pod."""
        try:
            events = self.core_v1.list_namespaced_event(
                namespace=namespace,
                field_selector=f"involvedObject.name={pod_name}"
            )
            return [
                {
                    "type": e.type,
                    "reason": e.reason,
                    "message": e.message,
                    "count": e.count,
                    "first_timestamp": e.first_timestamp,
                    "last_timestamp": e.last_timestamp,
                }
                for e in events.items
            ]
        except ApiException:
            return []

    def list_deployments(self, namespace: str = "default") -> str:
        """List all deployments in a namespace.

        Args:
            namespace: The namespace to list deployments from

        Returns:
            JSON string with deployment information
        """
        try:
            deployments = self.apps_v1.list_namespaced_deployment(namespace=namespace)
            deploy_list = []
            for deploy in deployments.items:
                deploy_info = {
                    "name": deploy.metadata.name,
                    "namespace": deploy.metadata.namespace,
                    "replicas": deploy.spec.replicas,
                    "ready_replicas": deploy.status.ready_replicas or 0,
                    "available_replicas": deploy.status.available_replicas or 0,
                }
                deploy_list.append(deploy_info)
            return json.dumps({"deployments": deploy_list}, indent=2)
        except ApiException as e:
            return json.dumps({"error": str(e)}, indent=2)

    def scale_deployment(self, name: str, replicas: int, namespace: str = "default") -> str:
        """Scale a deployment to a specific number of replicas.

        Args:
            name: Deployment name
            replicas: Target number of replicas
            namespace: Namespace the deployment is in

        Returns:
            JSON string with the result
        """
        try:
            # Read the deployment
            deployment = self.apps_v1.read_namespaced_deployment(name=name, namespace=namespace)

            # Update replicas
            deployment.spec.replicas = replicas

            # Patch the deployment
            self.apps_v1.patch_namespaced_deployment(
                name=name,
                namespace=namespace,
                body=deployment
            )

            return json.dumps({
                "success": True,
                "deployment": name,
                "replicas": replicas,
                "namespace": namespace
            }, indent=2)
        except ApiException as e:
            return json.dumps({"error": str(e)}, indent=2)

    def list_namespaces(self) -> str:
        """List all namespaces in the cluster.

        Returns:
            JSON string with namespace information
        """
        try:
            namespaces = self.core_v1.list_namespace()
            ns_list = [
                {
                    "name": ns.metadata.name,
                    "status": ns.status.phase,
                }
                for ns in namespaces.items
            ]
            return json.dumps({"namespaces": ns_list}, indent=2)
        except ApiException as e:
            return json.dumps({"error": str(e)}, indent=2)

    def apply_manifest(self, yaml_content: str, namespace: str = "default") -> str:
        """Apply a Kubernetes YAML manifest.

        Args:
            yaml_content: YAML content to apply
            namespace: Default namespace for resources without one specified

        Returns:
            JSON string with results of the apply operation
        """
        try:
            # Parse YAML (can be multiple documents)
            manifests = list(yaml.safe_load_all(yaml_content))
            results = []

            for manifest in manifests:
                if not manifest:
                    continue

                # Get resource info
                kind = manifest.get("kind")
                api_version = manifest.get("apiVersion")
                metadata = manifest.get("metadata", {})
                name = metadata.get("name", "unknown")
                resource_namespace = metadata.get("namespace", namespace)

                # Set namespace if not present and not a cluster-scoped resource
                if "namespace" not in metadata and kind not in ["Namespace", "ClusterRole", "ClusterRoleBinding"]:
                    manifest["metadata"]["namespace"] = resource_namespace

                # Get the resource type from the dynamic client
                api = self.dynamic_client.resources.get(
                    api_version=api_version, kind=kind
                )

                # Try to create the resource
                try:
                    if hasattr(api, "create"):
                        if kind in ["Namespace", "ClusterRole", "ClusterRoleBinding"]:
                            resp = api.create(body=manifest)
                        else:
                            resp = api.create(body=manifest, namespace=resource_namespace)
                        results.append({
                            "action": "created",
                            "kind": kind,
                            "name": name,
                            "namespace": resource_namespace,
                        })
                    else:
                        results.append({
                            "action": "error",
                            "kind": kind,
                            "name": name,
                            "error": "Resource type does not support create",
                        })
                except Exception as create_error:
                    # If create fails (resource exists), try to patch
                    if "already exists" in str(create_error).lower():
                        try:
                            if kind in ["Namespace", "ClusterRole", "ClusterRoleBinding"]:
                                resp = api.patch(body=manifest, name=name)
                            else:
                                resp = api.patch(
                                    body=manifest, name=name, namespace=resource_namespace
                                )
                            results.append({
                                "action": "updated",
                                "kind": kind,
                                "name": name,
                                "namespace": resource_namespace,
                            })
                        except Exception as patch_error:
                            results.append({
                                "action": "error",
                                "kind": kind,
                                "name": name,
                                "error": str(patch_error),
                            })
                    else:
                        results.append({
                            "action": "error",
                            "kind": kind,
                            "name": name,
                            "error": str(create_error),
                        })

            return json.dumps({"success": True, "results": results}, indent=2)

        except yaml.YAMLError as e:
            return json.dumps({"success": False, "error": f"Invalid YAML: {str(e)}"}, indent=2)
        except Exception as e:
            return json.dumps({"success": False, "error": str(e)}, indent=2)

    def delete_resource(
        self, kind: str, name: str, namespace: str = "default", api_version: str = None
    ) -> str:
        """Delete a Kubernetes resource.

        Args:
            kind: Resource kind (e.g., Pod, Deployment, Service)
            name: Resource name
            namespace: Namespace (ignored for cluster-scoped resources)
            api_version: API version (e.g., v1, apps/v1). Will be inferred if not provided.

        Returns:
            JSON string with deletion result
        """
        try:
            # Infer common API versions if not provided
            if not api_version:
                api_version_map = {
                    "Pod": "v1",
                    "Service": "v1",
                    "ConfigMap": "v1",
                    "Secret": "v1",
                    "Namespace": "v1",
                    "Deployment": "apps/v1",
                    "StatefulSet": "apps/v1",
                    "DaemonSet": "apps/v1",
                }
                api_version = api_version_map.get(kind, "v1")

            # Get the resource type
            api = self.dynamic_client.resources.get(api_version=api_version, kind=kind)

            # Delete the resource
            if kind in ["Namespace", "ClusterRole", "ClusterRoleBinding"]:
                api.delete(name=name)
            else:
                api.delete(name=name, namespace=namespace)

            return json.dumps({
                "success": True,
                "deleted": True,
                "kind": kind,
                "name": name,
                "namespace": namespace,
            }, indent=2)

        except ResourceNotFoundError:
            return json.dumps({
                "success": False,
                "error": f"{kind} '{name}' not found",
            }, indent=2)
        except Exception as e:
            return json.dumps({
                "success": False,
                "error": str(e),
            }, indent=2)

    def get_resource(
        self, kind: str, name: str, namespace: str = "default", api_version: str = None
    ) -> str:
        """Get details about any Kubernetes resource.

        Args:
            kind: Resource kind (e.g., Pod, Deployment, Service)
            name: Resource name
            namespace: Namespace (ignored for cluster-scoped resources)
            api_version: API version. Will be inferred if not provided.

        Returns:
            JSON string with resource details
        """
        try:
            # Infer common API versions if not provided
            if not api_version:
                api_version_map = {
                    "Pod": "v1",
                    "Service": "v1",
                    "ConfigMap": "v1",
                    "Secret": "v1",
                    "Namespace": "v1",
                    "Deployment": "apps/v1",
                    "StatefulSet": "apps/v1",
                    "DaemonSet": "apps/v1",
                }
                api_version = api_version_map.get(kind, "v1")

            # Get the resource type
            api = self.dynamic_client.resources.get(api_version=api_version, kind=kind)

            # Get the resource
            if kind in ["Namespace", "ClusterRole", "ClusterRoleBinding"]:
                resource = api.get(name=name)
            else:
                resource = api.get(name=name, namespace=namespace)

            # Convert to dict and return
            return json.dumps(resource.to_dict(), indent=2, default=str)

        except ResourceNotFoundError:
            return json.dumps({
                "success": False,
                "error": f"{kind} '{name}' not found",
            }, indent=2)
        except Exception as e:
            return json.dumps({
                "success": False,
                "error": str(e),
            }, indent=2)


# Read-only tool definitions for OpenAI API
READ_ONLY_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "list_pods",
            "description": "List all pods in a Kubernetes namespace. Returns pod names, status, restart counts, and container information.",
            "parameters": {
                "type": "object",
                "properties": {
                    "namespace": {
                        "type": "string",
                        "description": "The namespace to list pods from. Defaults to 'default'.",
                        "default": "default"
                    }
                },
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_pod_logs",
            "description": "Retrieve logs from a specific pod. Useful for debugging issues.",
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {
                        "type": "string",
                        "description": "The name of the pod to get logs from"
                    },
                    "namespace": {
                        "type": "string",
                        "description": "The namespace the pod is in. Defaults to 'default'.",
                        "default": "default"
                    },
                    "tail_lines": {
                        "type": "integer",
                        "description": "Number of lines to retrieve from the end of logs. Defaults to 100.",
                        "default": 100
                    }
                },
                "required": ["name"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "describe_pod",
            "description": "Get detailed information about a specific pod including container status, conditions, and recent events.",
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {
                        "type": "string",
                        "description": "The name of the pod to describe"
                    },
                    "namespace": {
                        "type": "string",
                        "description": "The namespace the pod is in. Defaults to 'default'.",
                        "default": "default"
                    }
                },
                "required": ["name"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "list_deployments",
            "description": "List all deployments in a namespace with their replica counts and availability status.",
            "parameters": {
                "type": "object",
                "properties": {
                    "namespace": {
                        "type": "string",
                        "description": "The namespace to list deployments from. Defaults to 'default'.",
                        "default": "default"
                    }
                },
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "list_namespaces",
            "description": "List all namespaces in the cluster.",
            "parameters": {
                "type": "object",
                "properties": {}
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_resource",
            "description": "Get detailed information about any Kubernetes resource by kind and name.",
            "parameters": {
                "type": "object",
                "properties": {
                    "kind": {
                        "type": "string",
                        "description": "Resource kind (e.g., Pod, Deployment, Service)"
                    },
                    "name": {
                        "type": "string",
                        "description": "Resource name"
                    },
                    "namespace": {
                        "type": "string",
                        "description": "Namespace (ignored for cluster-scoped resources). Defaults to 'default'.",
                        "default": "default"
                    },
                    "api_version": {
                        "type": "string",
                        "description": "API version. Will be inferred if not provided."
                    }
                },
                "required": ["kind", "name"]
            }
        }
    },
]

# Mutating tool definitions - these require user approval before execution
MUTATING_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "scale_deployment",
            "description": "Scale a deployment to a specific number of replicas. Use with caution as this modifies cluster state.",
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {
                        "type": "string",
                        "description": "The name of the deployment to scale"
                    },
                    "replicas": {
                        "type": "integer",
                        "description": "The target number of replicas"
                    },
                    "namespace": {
                        "type": "string",
                        "description": "The namespace the deployment is in. Defaults to 'default'.",
                        "default": "default"
                    }
                },
                "required": ["name", "replicas"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "apply_manifest",
            "description": "Apply a Kubernetes YAML manifest to create or update resources. You can generate YAML manifests yourself and apply them using this tool.",
            "parameters": {
                "type": "object",
                "properties": {
                    "yaml_content": {
                        "type": "string",
                        "description": "The YAML manifest content to apply"
                    },
                    "namespace": {
                        "type": "string",
                        "description": "Default namespace for resources without one specified. Defaults to 'default'.",
                        "default": "default"
                    }
                },
                "required": ["yaml_content"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "delete_resource",
            "description": "Delete a Kubernetes resource by kind and name.",
            "parameters": {
                "type": "object",
                "properties": {
                    "kind": {
                        "type": "string",
                        "description": "Resource kind (e.g., Pod, Deployment, Service)"
                    },
                    "name": {
                        "type": "string",
                        "description": "Resource name"
                    },
                    "namespace": {
                        "type": "string",
                        "description": "Namespace (ignored for cluster-scoped resources). Defaults to 'default'.",
                        "default": "default"
                    },
                    "api_version": {
                        "type": "string",
                        "description": "API version (e.g., v1, apps/v1). Will be inferred if not provided."
                    }
                },
                "required": ["kind", "name"]
            }
        }
    },
]

# Combined tools for backward compatibility
TOOLS = READ_ONLY_TOOLS + MUTATING_TOOLS
