"""
Agent Tools - Functions the agent can use with delegated permissions

These tools demonstrate how the agent uses OAuth2 tokens to act on behalf of users.
"""

import logging
from typing import Any, Dict
import requests

logger = logging.getLogger(__name__)


class AgentTools:
    """Tools that the agent can use to interact with services on behalf of users."""

    def __init__(self, demo_service_url: str):
        """
        Initialize agent tools.

        Args:
            demo_service_url: URL of the demo API service
        """
        self.demo_service_url = demo_service_url

    def get_tools_definition(self) -> list[Dict[str, Any]]:
        """
        Return tool definitions for Claude's tool calling API.

        Returns:
            List of tool definitions
        """
        return [
            {
                "name": "whoami",
                "description": "Get information about the current user. This uses the delegated OAuth2 token to identify who the agent is acting as.",
                "input_schema": {
                    "type": "object",
                    "properties": {},
                    "required": []
                }
            },
            {
                "name": "list_tasks",
                "description": "List all tasks for the current user. Uses the user's delegated permissions to fetch their tasks.",
                "input_schema": {
                    "type": "object",
                    "properties": {},
                    "required": []
                }
            },
            {
                "name": "create_task",
                "description": "Create a new task for the current user. Uses delegated permissions to create a task on the user's behalf.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "title": {
                            "type": "string",
                            "description": "The title of the task to create"
                        }
                    },
                    "required": ["title"]
                }
            },
            {
                "name": "perform_action",
                "description": "Perform a protected action on behalf of the user. This demonstrates the agent using delegated permissions to take actions.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "action": {
                            "type": "string",
                            "description": "The action to perform (e.g., 'backup_data', 'send_report', 'cleanup')"
                        }
                    },
                    "required": ["action"]
                }
            }
        ]

    def execute_tool(self, tool_name: str, tool_input: Dict[str, Any], access_token: str) -> str:
        """
        Execute a tool call using the provided access token.

        Args:
            tool_name: Name of the tool to execute
            tool_input: Input parameters for the tool
            access_token: OAuth2 access token for the user

        Returns:
            Result of the tool execution as a string
        """
        headers = {"Authorization": f"Bearer {access_token}"}

        try:
            if tool_name == "whoami":
                return self._whoami(headers)
            elif tool_name == "list_tasks":
                return self._list_tasks(headers)
            elif tool_name == "create_task":
                return self._create_task(tool_input["title"], headers)
            elif tool_name == "perform_action":
                return self._perform_action(tool_input["action"], headers)
            else:
                return f"Error: Unknown tool '{tool_name}'"

        except Exception as e:
            logger.error(f"Tool execution failed: {e}")
            return f"Error executing {tool_name}: {str(e)}"

    def _whoami(self, headers: Dict[str, str]) -> str:
        """Get user information."""
        response = requests.get(
            f"{self.demo_service_url}/api/whoami",
            headers=headers,
            timeout=10
        )
        response.raise_for_status()
        data = response.json()

        return f"""Successfully identified user:
- Username: {data['user']['username']}
- Email: {data['user']['email']}
- Message: {data['message']}

This request used the delegated OAuth2 token to verify the user's identity."""

    def _list_tasks(self, headers: Dict[str, str]) -> str:
        """List user's tasks."""
        response = requests.get(
            f"{self.demo_service_url}/api/tasks",
            headers=headers,
            timeout=10
        )
        response.raise_for_status()
        data = response.json()

        tasks_str = "\n".join([
            f"  {t['id']}. {t['title']} [{t['status']}]"
            for t in data['tasks']
        ])

        return f"""Tasks for user {data['user']}:
{tasks_str}

Retrieved using delegated permissions."""

    def _create_task(self, title: str, headers: Dict[str, str]) -> str:
        """Create a new task."""
        response = requests.post(
            f"{self.demo_service_url}/api/tasks",
            headers=headers,
            json={"title": title},
            timeout=10
        )
        response.raise_for_status()
        data = response.json()

        return f"""Successfully created task:
- ID: {data['task']['id']}
- Title: {data['task']['title']}
- Owner: {data['task']['owner']}
- Status: {data['task']['status']}

Created using delegated user permissions."""

    def _perform_action(self, action: str, headers: Dict[str, str]) -> str:
        """Perform a protected action."""
        response = requests.post(
            f"{self.demo_service_url}/api/protected-action",
            headers=headers,
            json={"action": action},
            timeout=10
        )
        response.raise_for_status()
        data = response.json()

        return f"""Action completed:
- Action: {action}
- Performed by: {data['performed_by']}
- Message: {data['message']}

This action was performed with the user's delegated permissions."""
