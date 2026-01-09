"""Testing and verification tools for the devoops agent."""

import json
import time
import requests
from kubernetes import client
from kubernetes.client.rest import ApiException
from kubernetes.stream import stream


class TestingClient:
    """Client for testing and verifying deployed resources."""

    def __init__(self, core_v1: client.CoreV1Api):
        """Initialize the testing client.

        Args:
            core_v1: CoreV1Api instance to use
        """
        self.core_v1 = core_v1

    def http_request(
        self,
        url: str,
        method: str = "GET",
        headers: dict = None,
        body: str = None,
        timeout: int = 10,
    ) -> str:
        """Make an HTTP request to test endpoints.

        Args:
            url: URL to request (typically a service URL like http://nginx.default.svc.cluster.local)
            method: HTTP method (GET, POST, etc.)
            headers: Optional headers dict
            body: Optional request body
            timeout: Request timeout in seconds

        Returns:
            JSON string with response details
        """
        try:
            response = requests.request(
                method=method.upper(),
                url=url,
                headers=headers or {},
                data=body,
                timeout=timeout,
                allow_redirects=True,
            )

            return json.dumps(
                {
                    "success": True,
                    "status_code": response.status_code,
                    "headers": dict(response.headers),
                    "body": response.text[:1000],  # Limit body size
                    "url": url,
                },
                indent=2,
            )
        except requests.exceptions.RequestException as e:
            return json.dumps(
                {
                    "success": False,
                    "error": str(e),
                    "url": url,
                },
                indent=2,
            )

    def exec_in_pod(
        self, pod_name: str, command: list, namespace: str = "default", container: str = None
    ) -> str:
        """Execute a command in a pod.

        Args:
            pod_name: Name of the pod
            command: Command to execute as a list (e.g., ["ls", "-la"])
            namespace: Namespace the pod is in
            container: Optional container name (uses first container if not specified)

        Returns:
            JSON string with command output
        """
        try:
            exec_command = command
            if container:
                resp = stream(
                    self.core_v1.connect_get_namespaced_pod_exec,
                    pod_name,
                    namespace,
                    container=container,
                    command=exec_command,
                    stderr=True,
                    stdin=False,
                    stdout=True,
                    tty=False,
                )
            else:
                resp = stream(
                    self.core_v1.connect_get_namespaced_pod_exec,
                    pod_name,
                    namespace,
                    command=exec_command,
                    stderr=True,
                    stdin=False,
                    stdout=True,
                    tty=False,
                )

            return json.dumps(
                {
                    "success": True,
                    "output": resp,
                    "pod": pod_name,
                    "namespace": namespace,
                    "command": " ".join(command),
                },
                indent=2,
            )
        except ApiException as e:
            return json.dumps(
                {
                    "success": False,
                    "error": str(e),
                    "pod": pod_name,
                    "namespace": namespace,
                },
                indent=2,
            )

    def wait_for_pod_ready(
        self, pod_name: str, namespace: str = "default", timeout: int = 60
    ) -> str:
        """Wait for a pod to be ready.

        Args:
            pod_name: Name of the pod to wait for
            namespace: Namespace the pod is in
            timeout: Maximum time to wait in seconds

        Returns:
            JSON string with readiness status
        """
        start_time = time.time()

        while time.time() - start_time < timeout:
            try:
                pod = self.core_v1.read_namespaced_pod(name=pod_name, namespace=namespace)

                # Check if pod is ready
                if pod.status.conditions:
                    for condition in pod.status.conditions:
                        if condition.type == "Ready" and condition.status == "True":
                            return json.dumps(
                                {
                                    "success": True,
                                    "ready": True,
                                    "pod": pod_name,
                                    "namespace": namespace,
                                    "wait_time": round(time.time() - start_time, 2),
                                },
                                indent=2,
                            )

                # Not ready yet, wait a bit
                time.sleep(2)

            except ApiException as e:
                return json.dumps(
                    {
                        "success": False,
                        "error": str(e),
                        "pod": pod_name,
                        "namespace": namespace,
                    },
                    indent=2,
                )

        # Timeout reached
        return json.dumps(
            {
                "success": False,
                "ready": False,
                "error": "Timeout waiting for pod to be ready",
                "pod": pod_name,
                "namespace": namespace,
                "timeout": timeout,
            },
            indent=2,
        )

    def check_service_endpoints(self, service_name: str, namespace: str = "default") -> str:
        """Check if a service has endpoints (backing pods).

        Args:
            service_name: Name of the service
            namespace: Namespace the service is in

        Returns:
            JSON string with endpoint information
        """
        try:
            endpoints = self.core_v1.read_namespaced_endpoints(
                name=service_name, namespace=namespace
            )

            endpoint_list = []
            if endpoints.subsets:
                for subset in endpoints.subsets:
                    if subset.addresses:
                        for address in subset.addresses:
                            for port in subset.ports or []:
                                endpoint_list.append(
                                    {
                                        "ip": address.ip,
                                        "port": port.port,
                                        "protocol": port.protocol,
                                        "target_pod": address.target_ref.name
                                        if address.target_ref
                                        else None,
                                    }
                                )

            return json.dumps(
                {
                    "success": True,
                    "service": service_name,
                    "namespace": namespace,
                    "endpoint_count": len(endpoint_list),
                    "endpoints": endpoint_list,
                    "has_endpoints": len(endpoint_list) > 0,
                },
                indent=2,
            )
        except ApiException as e:
            return json.dumps(
                {
                    "success": False,
                    "error": str(e),
                    "service": service_name,
                    "namespace": namespace,
                },
                indent=2,
            )


# Cluster parameter definition - added to K8s-dependent tools
_CLUSTER_PARAM = {
    "type": "string",
    "description": "Target cluster name. Use list_clusters to see available clusters."
}

# Read-only testing tools - these don't modify cluster state
READ_ONLY_TESTING_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "http_request",
            "description": "Make an HTTP request to test endpoints like services or ingresses. Use service DNS names like http://servicename.namespace.svc.cluster.local:port",
            "parameters": {
                "type": "object",
                "properties": {
                    "url": {
                        "type": "string",
                        "description": "URL to request (e.g., http://nginx.default.svc.cluster.local:80)",
                    },
                    "method": {
                        "type": "string",
                        "description": "HTTP method (GET, POST, etc.). Defaults to GET.",
                        "default": "GET",
                    },
                    "headers": {
                        "type": "object",
                        "description": "Optional HTTP headers as key-value pairs",
                    },
                    "body": {
                        "type": "string",
                        "description": "Optional request body",
                    },
                    "timeout": {
                        "type": "integer",
                        "description": "Request timeout in seconds. Defaults to 10.",
                        "default": 10,
                    },
                },
                "required": ["url"],
            },
        }
    },
    {
        "type": "function",
        "function": {
            "name": "wait_for_pod_ready",
            "description": "Wait for a pod to be in Ready state on the specified cluster. Use this before testing newly created pods.",
            "parameters": {
                "type": "object",
                "properties": {
                    "cluster": _CLUSTER_PARAM,
                    "pod_name": {
                        "type": "string",
                        "description": "Name of the pod to wait for",
                    },
                    "namespace": {
                        "type": "string",
                        "description": "Namespace the pod is in. Defaults to 'default'.",
                        "default": "default",
                    },
                    "timeout": {
                        "type": "integer",
                        "description": "Maximum time to wait in seconds. Defaults to 60.",
                        "default": 60,
                    },
                },
                "required": ["cluster", "pod_name"],
            },
        }
    },
    {
        "type": "function",
        "function": {
            "name": "check_service_endpoints",
            "description": "Check if a service has endpoints (backing pods) on the specified cluster. Useful for verifying that a service is properly configured.",
            "parameters": {
                "type": "object",
                "properties": {
                    "cluster": _CLUSTER_PARAM,
                    "service_name": {
                        "type": "string",
                        "description": "Name of the service to check",
                    },
                    "namespace": {
                        "type": "string",
                        "description": "Namespace the service is in. Defaults to 'default'.",
                        "default": "default",
                    },
                },
                "required": ["cluster", "service_name"],
            },
        }
    },
]

# Mutating testing tools - these can modify state and require approval
MUTATING_TESTING_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "exec_in_pod",
            "description": "Execute a command inside a pod on the specified cluster for testing or verification. Useful for checking connectivity, running tests, etc.",
            "parameters": {
                "type": "object",
                "properties": {
                    "cluster": _CLUSTER_PARAM,
                    "pod_name": {
                        "type": "string",
                        "description": "Name of the pod to execute command in",
                    },
                    "command": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Command to execute as an array (e.g., ['curl', 'http://google.com'])",
                    },
                    "namespace": {
                        "type": "string",
                        "description": "Namespace the pod is in. Defaults to 'default'.",
                        "default": "default",
                    },
                    "container": {
                        "type": "string",
                        "description": "Container name (uses first container if not specified)",
                    },
                },
                "required": ["cluster", "pod_name", "command"],
            },
        }
    },
]

# Combined tools for backward compatibility
TESTING_TOOLS = READ_ONLY_TESTING_TOOLS + MUTATING_TESTING_TOOLS
