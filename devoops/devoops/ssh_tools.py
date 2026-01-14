"""SSH tools for the devoops agent."""

import json
from typing import Optional, Dict, List

import paramiko

from devoops.ssh_config import SSHServerConfig, SSHKeyManager


class SSHClient:
    """Wrapper around paramiko SSH client with tool methods."""

    def __init__(
        self,
        server_config: SSHServerConfig,
        key_manager: SSHKeyManager,
        timeout: int = 30,
    ):
        """Initialize the SSH client.

        Args:
            server_config: Server configuration with host, port, username
            key_manager: Key manager with private key for authentication
            timeout: Connection and command timeout in seconds
        """
        self.server_config = server_config
        self.key_manager = key_manager
        self.timeout = timeout
        self._client: Optional[paramiko.SSHClient] = None

    def _connect(self) -> None:
        """Establish SSH connection if not already connected."""
        if self._client is not None:
            # Check if connection is still alive
            try:
                transport = self._client.get_transport()
                if transport and transport.is_active():
                    return
            except Exception:
                pass
            # Connection dead, close and reconnect
            try:
                self._client.close()
            except Exception:
                pass
            self._client = None

        self._client = paramiko.SSHClient()
        self._client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        self._client.connect(
            hostname=self.server_config.host,
            port=self.server_config.port,
            username=self.server_config.username,
            pkey=self.key_manager.get_private_key(),
            timeout=self.timeout,
        )

    def _exec(self, command: str) -> tuple[str, str, int]:
        """Execute command and return stdout, stderr, exit_code.

        Args:
            command: Shell command to execute

        Returns:
            Tuple of (stdout, stderr, exit_code)
        """
        self._connect()
        stdin, stdout, stderr = self._client.exec_command(
            command, timeout=self.timeout
        )
        exit_code = stdout.channel.recv_exit_status()
        return (
            stdout.read().decode("utf-8", errors="replace"),
            stderr.read().decode("utf-8", errors="replace"),
            exit_code,
        )

    def _format_result(
        self,
        stdout: str,
        stderr: str,
        exit_code: int,
        command: str = None,
    ) -> str:
        """Format command result as JSON string."""
        result = {
            "success": exit_code == 0,
            "exit_code": exit_code,
            "stdout": stdout,
            "server": self.server_config.name,
        }
        if stderr:
            result["stderr"] = stderr
        if command:
            result["command"] = command
        return json.dumps(result, indent=2)

    def _handle_error(self, error: Exception, operation: str) -> str:
        """Format error as JSON string."""
        return json.dumps({
            "success": False,
            "error": f"{operation} failed: {str(error)}",
            "server": self.server_config.name,
        }, indent=2)

    # Read-only operations

    def list_files(self, path: str = "/", options: str = "-la") -> str:
        """List files and directories.

        Args:
            path: Directory path to list
            options: ls command options (e.g., '-la', '-lh')

        Returns:
            JSON string with file listing
        """
        try:
            # Sanitize options to prevent injection
            safe_options = options.replace(";", "").replace("&", "").replace("|", "")
            safe_path = path.replace(";", "").replace("&", "").replace("|", "")
            command = f"ls {safe_options} {safe_path}"
            stdout, stderr, exit_code = self._exec(command)
            return self._format_result(stdout, stderr, exit_code, command)
        except Exception as e:
            return self._handle_error(e, "list_files")

    def read_file(self, path: str, max_lines: int = 1000) -> str:
        """Read file contents with line limit.

        Args:
            path: File path to read
            max_lines: Maximum number of lines to read

        Returns:
            JSON string with file contents
        """
        try:
            safe_path = path.replace(";", "").replace("&", "").replace("|", "")
            command = f"head -n {max_lines} {safe_path}"
            stdout, stderr, exit_code = self._exec(command)
            return self._format_result(stdout, stderr, exit_code, command)
        except Exception as e:
            return self._handle_error(e, "read_file")

    def list_processes(self, filter_str: Optional[str] = None) -> str:
        """List running processes.

        Args:
            filter_str: Optional grep filter for process list

        Returns:
            JSON string with process listing
        """
        try:
            if filter_str:
                safe_filter = filter_str.replace(";", "").replace("&", "").replace("|", "").replace("'", "")
                command = f"ps aux | grep -i '{safe_filter}' | grep -v grep"
            else:
                command = "ps aux"
            stdout, stderr, exit_code = self._exec(command)
            # grep returns exit 1 if no matches, treat as success with empty output
            if filter_str and exit_code == 1 and not stderr:
                exit_code = 0
                stdout = "(no matching processes)"
            return self._format_result(stdout, stderr, exit_code, command)
        except Exception as e:
            return self._handle_error(e, "list_processes")

    def check_service(self, service_name: str) -> str:
        """Check systemd service status.

        Args:
            service_name: Name of the systemd service

        Returns:
            JSON string with service status
        """
        try:
            safe_name = service_name.replace(";", "").replace("&", "").replace("|", "").replace(" ", "")
            command = f"systemctl status {safe_name}"
            stdout, stderr, exit_code = self._exec(command)
            # systemctl status returns non-zero for inactive services, still valid
            return self._format_result(stdout, stderr, exit_code, command)
        except Exception as e:
            return self._handle_error(e, "check_service")

    def disk_usage(self) -> str:
        """Get disk usage information.

        Returns:
            JSON string with disk usage info
        """
        try:
            command = "df -h"
            stdout, stderr, exit_code = self._exec(command)
            return self._format_result(stdout, stderr, exit_code, command)
        except Exception as e:
            return self._handle_error(e, "disk_usage")

    def memory_info(self) -> str:
        """Get memory usage information.

        Returns:
            JSON string with memory info
        """
        try:
            command = "free -h"
            stdout, stderr, exit_code = self._exec(command)
            return self._format_result(stdout, stderr, exit_code, command)
        except Exception as e:
            return self._handle_error(e, "memory_info")

    def uptime(self) -> str:
        """Get system uptime.

        Returns:
            JSON string with uptime info
        """
        try:
            command = "uptime"
            stdout, stderr, exit_code = self._exec(command)
            return self._format_result(stdout, stderr, exit_code, command)
        except Exception as e:
            return self._handle_error(e, "uptime")

    def tail_log(self, log_path: str, lines: int = 100) -> str:
        """Read last N lines of a log file.

        Args:
            log_path: Path to the log file
            lines: Number of lines to read from end

        Returns:
            JSON string with log contents
        """
        try:
            safe_path = log_path.replace(";", "").replace("&", "").replace("|", "")
            command = f"tail -n {lines} {safe_path}"
            stdout, stderr, exit_code = self._exec(command)
            return self._format_result(stdout, stderr, exit_code, command)
        except Exception as e:
            return self._handle_error(e, "tail_log")

    # Mutating operations (require approval)

    def exec_command(self, command: str) -> str:
        """Execute arbitrary command on the server.

        Args:
            command: Shell command to execute

        Returns:
            JSON string with command output
        """
        try:
            stdout, stderr, exit_code = self._exec(command)
            return self._format_result(stdout, stderr, exit_code, command)
        except Exception as e:
            return self._handle_error(e, "exec_command")

    def close(self) -> None:
        """Close the SSH connection."""
        if self._client:
            try:
                self._client.close()
            except Exception:
                pass
            self._client = None


class SSHServerRegistry:
    """Manages SSHClient instances for multiple servers."""

    def __init__(
        self,
        servers: List[SSHServerConfig],
        key_manager: SSHKeyManager,
        default_server: Optional[str] = None,
    ):
        """Initialize the registry.

        Args:
            servers: List of server configurations
            key_manager: Key manager with SSH keypair
            default_server: Name of default server (None means server is required)
        """
        self.servers = {s.name: s for s in servers}
        self.key_manager = key_manager
        self.default_server = default_server
        self._clients: Dict[str, SSHClient] = {}

    def get_server_names(self) -> List[str]:
        """Get list of available server names."""
        return list(self.servers.keys())

    def get_server_info(self) -> List[dict]:
        """Get sanitized info about all servers for API responses."""
        return [s.to_dict() for s in self.servers.values()]

    def get_client(self, server_name: str) -> SSHClient:
        """Get or create an SSHClient for the specified server.

        Args:
            server_name: Name of the server

        Returns:
            SSHClient configured for the server

        Raises:
            ValueError: If server name is unknown
        """
        if server_name not in self.servers:
            raise ValueError(
                f"Unknown server: {server_name}. "
                f"Available: {list(self.servers.keys())}"
            )

        if server_name not in self._clients:
            server_config = self.servers[server_name]
            self._clients[server_name] = SSHClient(
                server_config=server_config,
                key_manager=self.key_manager,
            )

        return self._clients[server_name]

    def resolve_server(self, server_name: Optional[str]) -> str:
        """Resolve server name, using default if not specified.

        Args:
            server_name: Explicit server name or None

        Returns:
            Resolved server name

        Raises:
            ValueError: If server not specified and no default configured
        """
        if server_name:
            if server_name not in self.servers:
                raise ValueError(
                    f"Unknown server: {server_name}. "
                    f"Available: {list(self.servers.keys())}"
                )
            return server_name

        if self.default_server:
            return self.default_server

        raise ValueError(
            f"Server must be specified. Available servers: {list(self.servers.keys())}"
        )


# Server parameter definition - added to all SSH tools
_SERVER_PARAM = {
    "type": "string",
    "description": "Target SSH server name. Use list_ssh_servers to see available servers."
}

# Server discovery tool
SSH_DISCOVERY_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "list_ssh_servers",
            "description": "List all available SSH servers that the agent can connect to. Call this first to discover server names before using other SSH tools.",
            "parameters": {
                "type": "object",
                "properties": {}
            }
        }
    }
]

# Read-only tool definitions
READ_ONLY_SSH_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "ssh_list_files",
            "description": "List files and directories on the specified SSH server.",
            "parameters": {
                "type": "object",
                "properties": {
                    "server": _SERVER_PARAM,
                    "path": {
                        "type": "string",
                        "description": "Directory path to list. Defaults to '/'.",
                        "default": "/"
                    },
                    "options": {
                        "type": "string",
                        "description": "ls command options (e.g., '-la', '-lh'). Defaults to '-la'.",
                        "default": "-la"
                    }
                },
                "required": ["server"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "ssh_read_file",
            "description": "Read the contents of a file on the specified SSH server. Limited to first N lines to prevent large outputs.",
            "parameters": {
                "type": "object",
                "properties": {
                    "server": _SERVER_PARAM,
                    "path": {
                        "type": "string",
                        "description": "File path to read"
                    },
                    "max_lines": {
                        "type": "integer",
                        "description": "Maximum number of lines to read. Defaults to 1000.",
                        "default": 1000
                    }
                },
                "required": ["server", "path"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "ssh_list_processes",
            "description": "List running processes on the specified SSH server. Optionally filter by process name.",
            "parameters": {
                "type": "object",
                "properties": {
                    "server": _SERVER_PARAM,
                    "filter": {
                        "type": "string",
                        "description": "Optional filter string to grep process list (case-insensitive)"
                    }
                },
                "required": ["server"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "ssh_check_service",
            "description": "Check the status of a systemd service on the specified SSH server.",
            "parameters": {
                "type": "object",
                "properties": {
                    "server": _SERVER_PARAM,
                    "service_name": {
                        "type": "string",
                        "description": "Name of the systemd service (e.g., 'nginx', 'sshd', 'docker')"
                    }
                },
                "required": ["server", "service_name"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "ssh_disk_usage",
            "description": "Get disk usage information (df -h) from the specified SSH server.",
            "parameters": {
                "type": "object",
                "properties": {
                    "server": _SERVER_PARAM
                },
                "required": ["server"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "ssh_memory_info",
            "description": "Get memory usage information (free -h) from the specified SSH server.",
            "parameters": {
                "type": "object",
                "properties": {
                    "server": _SERVER_PARAM
                },
                "required": ["server"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "ssh_uptime",
            "description": "Get system uptime and load average from the specified SSH server.",
            "parameters": {
                "type": "object",
                "properties": {
                    "server": _SERVER_PARAM
                },
                "required": ["server"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "ssh_tail_log",
            "description": "Read the last N lines of a log file on the specified SSH server.",
            "parameters": {
                "type": "object",
                "properties": {
                    "server": _SERVER_PARAM,
                    "log_path": {
                        "type": "string",
                        "description": "Path to the log file (e.g., '/var/log/syslog', '/var/log/nginx/error.log')"
                    },
                    "lines": {
                        "type": "integer",
                        "description": "Number of lines to read from end. Defaults to 100.",
                        "default": 100
                    }
                },
                "required": ["server", "log_path"]
            }
        }
    },
]

# Mutating tool definitions - require user approval before execution
MUTATING_SSH_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "ssh_exec",
            "description": "Execute an arbitrary shell command on the specified SSH server. This is a mutating operation that requires plan approval. Use for operations like restarting services, installing packages, or modifying files.",
            "parameters": {
                "type": "object",
                "properties": {
                    "server": _SERVER_PARAM,
                    "command": {
                        "type": "string",
                        "description": "The shell command to execute"
                    }
                },
                "required": ["server", "command"]
            }
        }
    }
]
