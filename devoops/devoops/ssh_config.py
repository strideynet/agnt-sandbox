"""SSH server configuration management."""

import os
import yaml
from dataclasses import dataclass
from typing import Optional, List

import paramiko


@dataclass
class SSHServerConfig:
    """Configuration for a single SSH server."""
    name: str
    display_name: str
    description: str
    host: str
    port: int = 22
    username: str = "root"

    def to_dict(self) -> dict:
        """Convert to API-safe dictionary."""
        return {
            "name": self.name,
            "displayName": self.display_name,
            "description": self.description,
            "host": self.host,
            "port": self.port,
            "username": self.username,
        }


class SSHConfigError(Exception):
    """Raised when SSH configuration is invalid."""
    pass


def load_ssh_config(
    config_path: str = "/etc/devoops/ssh-servers.yaml",
) -> tuple[List[SSHServerConfig], Optional[str]]:
    """Load and validate SSH server configuration from YAML file.

    Args:
        config_path: Path to the ssh-servers.yaml file

    Returns:
        Tuple of (list of SSHServerConfig, default_server_name or None)

    Raises:
        SSHConfigError: If configuration is invalid
    """
    if not os.path.exists(config_path):
        # SSH config is optional - return empty list if not present
        return [], None

    with open(config_path, "r") as f:
        config = yaml.safe_load(f)

    if not config:
        return [], None

    servers_data = config.get("servers", [])
    if not servers_data:
        return [], None

    servers = []
    seen_names = set()

    for server_data in servers_data:
        # Validate required fields
        if "name" not in server_data:
            raise SSHConfigError("Each server must have a 'name' field")

        name = server_data["name"]
        if name in seen_names:
            raise SSHConfigError(f"Duplicate server name: {name}")
        seen_names.add(name)

        if "host" not in server_data:
            raise SSHConfigError(f"Server '{name}' must have a 'host' field")

        server = SSHServerConfig(
            name=name,
            display_name=server_data.get("displayName", name),
            description=server_data.get("description", ""),
            host=server_data["host"],
            port=server_data.get("port", 22),
            username=server_data.get("username", "root"),
        )
        servers.append(server)

    default_server = config.get("defaultServer")
    if default_server and default_server not in seen_names:
        raise SSHConfigError(
            f"Default server '{default_server}' not found in server list"
        )

    return servers, default_server


class SSHKeyManager:
    """Manages the agent's SSH keypair for authentication."""

    def __init__(self, key_path: str = "/etc/devoops/ssh-keys"):
        """Initialize the key manager.

        Args:
            key_path: Directory containing id_ed25519 and id_ed25519.pub files
        """
        self.key_path = key_path
        self.private_key_file = os.path.join(key_path, "id_ed25519")
        self.public_key_file = os.path.join(key_path, "id_ed25519.pub")
        self._private_key: Optional[paramiko.Ed25519Key] = None
        self._public_key_str: Optional[str] = None

    def load_keys(self) -> None:
        """Load existing keys from disk.

        Raises:
            SSHConfigError: If keys cannot be loaded
        """
        if not os.path.exists(self.private_key_file):
            raise SSHConfigError(
                f"SSH private key not found at {self.private_key_file}. "
                "Please create a key secret with: "
                "ssh-keygen -t ed25519 -f id_ed25519 -N '' && "
                "kubectl create secret generic devoops-ssh-keys "
                "--from-file=id_ed25519 --from-file=id_ed25519.pub -n devoops"
            )

        try:
            self._private_key = paramiko.Ed25519Key.from_private_key_file(
                self.private_key_file
            )
        except Exception as e:
            raise SSHConfigError(f"Failed to load SSH private key: {e}")

        # Load public key string for API exposure
        if os.path.exists(self.public_key_file):
            with open(self.public_key_file, "r") as f:
                self._public_key_str = f.read().strip()
        else:
            # Generate public key string from private key
            self._public_key_str = f"ssh-ed25519 {self._private_key.get_base64()} devoops-agent"

    def get_public_key_openssh(self) -> str:
        """Get public key in OpenSSH format for authorized_keys.

        Returns:
            Public key string in OpenSSH format
        """
        if self._public_key_str is None:
            raise SSHConfigError("Keys not loaded. Call load_keys() first.")
        return self._public_key_str

    def get_private_key(self) -> paramiko.Ed25519Key:
        """Get private key for paramiko authentication.

        Returns:
            Paramiko Ed25519Key object
        """
        if self._private_key is None:
            raise SSHConfigError("Keys not loaded. Call load_keys() first.")
        return self._private_key
