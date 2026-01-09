"""Cluster configuration management for multi-cluster support."""

import os
import yaml
from dataclasses import dataclass
from typing import Optional, List
from enum import Enum


class AuthType(str, Enum):
    """Authentication type for connecting to a cluster."""
    AMBIENT = "ambient"
    CERTIFICATE = "certificate"
    TOKEN = "token"


@dataclass
class ClusterAuth:
    """Authentication configuration for a cluster."""
    type: AuthType
    server: Optional[str] = None
    certificate_authority_data: Optional[str] = None
    client_certificate_data: Optional[str] = None
    client_key_data: Optional[str] = None
    token: Optional[str] = None


@dataclass
class ClusterConfig:
    """Configuration for a single Kubernetes cluster."""
    name: str
    display_name: str
    description: str
    auth: ClusterAuth
    impersonate_group: str = "devoops-users"

    def to_dict(self) -> dict:
        """Convert to API-safe dictionary (hides sensitive data)."""
        return {
            "name": self.name,
            "displayName": self.display_name,
            "description": self.description,
            "authType": self.auth.type.value,
            "impersonateGroup": self.impersonate_group,
        }


class ClusterConfigError(Exception):
    """Raised when cluster configuration is invalid."""
    pass


def load_cluster_config(
    config_path: str = "/etc/devoops/clusters.yaml",
) -> tuple[List[ClusterConfig], Optional[str]]:
    """Load and validate cluster configuration from YAML file.

    Args:
        config_path: Path to the clusters.yaml file

    Returns:
        Tuple of (list of ClusterConfig, default_cluster_name or None)

    Raises:
        ClusterConfigError: If configuration is invalid
    """
    if not os.path.exists(config_path):
        raise ClusterConfigError(f"Configuration file not found: {config_path}")

    with open(config_path, "r") as f:
        config = yaml.safe_load(f)

    if not config or "clusters" not in config:
        raise ClusterConfigError("Configuration must contain 'clusters' key")

    clusters = []
    seen_names = set()

    for cluster_data in config["clusters"]:
        # Validate required fields
        if "name" not in cluster_data:
            raise ClusterConfigError("Each cluster must have a 'name' field")

        name = cluster_data["name"]
        if name in seen_names:
            raise ClusterConfigError(f"Duplicate cluster name: {name}")
        seen_names.add(name)

        # Parse auth configuration
        auth_data = cluster_data.get("auth", {})
        auth_type_str = auth_data.get("type", "ambient")
        try:
            auth_type = AuthType(auth_type_str)
        except ValueError:
            raise ClusterConfigError(
                f"Invalid auth type '{auth_type_str}' for cluster '{name}'. "
                f"Must be one of: {', '.join(t.value for t in AuthType)}"
            )

        auth = ClusterAuth(
            type=auth_type,
            server=auth_data.get("server"),
            certificate_authority_data=auth_data.get("certificateAuthorityData"),
            client_certificate_data=auth_data.get("clientCertificateData"),
            client_key_data=auth_data.get("clientKeyData"),
            token=auth_data.get("token"),
        )

        # Validate auth configuration
        _validate_auth(name, auth)

        cluster = ClusterConfig(
            name=name,
            display_name=cluster_data.get("displayName", name),
            description=cluster_data.get("description", ""),
            auth=auth,
            impersonate_group=cluster_data.get("impersonateGroup", "devoops-users"),
        )
        clusters.append(cluster)

    if not clusters:
        raise ClusterConfigError("At least one cluster must be configured")

    default_cluster = config.get("defaultCluster")
    if default_cluster and default_cluster not in seen_names:
        raise ClusterConfigError(
            f"Default cluster '{default_cluster}' not found in cluster list"
        )

    return clusters, default_cluster


def _validate_auth(cluster_name: str, auth: ClusterAuth):
    """Validate authentication configuration.

    Args:
        cluster_name: Name of the cluster (for error messages)
        auth: Authentication configuration to validate

    Raises:
        ClusterConfigError: If configuration is invalid
    """
    if auth.type == AuthType.AMBIENT:
        # No additional validation needed for ambient auth
        return

    if auth.type == AuthType.CERTIFICATE:
        required = [
            ("server", auth.server),
            ("certificateAuthorityData", auth.certificate_authority_data),
            ("clientCertificateData", auth.client_certificate_data),
            ("clientKeyData", auth.client_key_data),
        ]
        for field_name, value in required:
            if not value:
                raise ClusterConfigError(
                    f"Cluster '{cluster_name}' with certificate auth requires '{field_name}'"
                )

    if auth.type == AuthType.TOKEN:
        required = [
            ("server", auth.server),
            ("certificateAuthorityData", auth.certificate_authority_data),
            ("token", auth.token),
        ]
        for field_name, value in required:
            if not value:
                raise ClusterConfigError(
                    f"Cluster '{cluster_name}' with token auth requires '{field_name}'"
                )
