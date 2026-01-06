"""Main agent implementation for devoops."""

import os
import logging
from anthropic import Anthropic
from devoops.k8s_tools import K8sClient, TOOLS
from devoops.test_tools import TestingClient, TESTING_TOOLS

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)


class DevoopsAgent:
    """The Devoops agent that executes missions in Kubernetes."""

    def __init__(self, api_key: str, in_cluster: bool = False):
        """Initialize the agent.

        Args:
            api_key: Anthropic API key
            in_cluster: Whether running in-cluster (use ServiceAccount) or local
        """
        self.client = Anthropic(api_key=api_key)
        self.k8s = K8sClient(in_cluster=in_cluster)
        self.testing = TestingClient(core_v1=self.k8s.core_v1)
        self.model = "claude-sonnet-4-20250514"

        # System prompt to encourage testing
        self.system_prompt = """You are a DevOps agent with the ability to manage Kubernetes resources and test your changes.

IMPORTANT: After making changes (creating/updating resources), you should verify they work correctly:
1. Use wait_for_pod_ready to ensure pods are running before testing
2. Use check_service_endpoints to verify services have backing pods
3. Use http_request to test HTTP endpoints
4. Use exec_in_pod to run commands inside pods for verification

Always test your changes when possible to ensure the mission succeeded."""

    def execute_mission(self, mission: str) -> str:
        """Execute a mission using Claude and Kubernetes tools.

        Args:
            mission: The mission prompt describing what to do

        Returns:
            The final response from the agent
        """
        logger.info(f"Starting mission: {mission}")

        messages = [{"role": "user", "content": mission}]

        # Agentic loop
        while True:
            response = self.client.messages.create(
                model=self.model,
                max_tokens=4096,
                tools=TOOLS + TESTING_TOOLS,  # Combine K8s and testing tools
                messages=messages,
                system=self.system_prompt,  # Add system prompt
            )

            logger.info(f"Stop reason: {response.stop_reason}")

            # Add assistant response to conversation
            messages.append({"role": "assistant", "content": response.content})

            # Check if we're done
            if response.stop_reason == "end_turn":
                # Extract final text response
                final_response = ""
                for block in response.content:
                    if hasattr(block, "text"):
                        final_response += block.text
                logger.info("Mission completed")
                return final_response

            # Process tool calls
            if response.stop_reason == "tool_use":
                tool_results = []

                for block in response.content:
                    if block.type == "tool_use":
                        tool_name = block.name
                        tool_input = block.input

                        logger.info(f"Executing tool: {tool_name} with input: {tool_input}")

                        # Execute the tool
                        try:
                            result = self._execute_tool(tool_name, tool_input)
                            logger.info(f"Tool result: {result[:200]}...")  # Log first 200 chars

                            tool_results.append({
                                "type": "tool_result",
                                "tool_use_id": block.id,
                                "content": result,
                            })
                        except Exception as e:
                            logger.error(f"Tool execution error: {e}")
                            tool_results.append({
                                "type": "tool_result",
                                "tool_use_id": block.id,
                                "content": f"Error executing tool: {str(e)}",
                                "is_error": True,
                            })

                # Add tool results to conversation
                messages.append({"role": "user", "content": tool_results})

            else:
                # Unexpected stop reason
                logger.warning(f"Unexpected stop reason: {response.stop_reason}")
                break

        return "Mission ended unexpectedly"

    def _execute_tool(self, tool_name: str, tool_input: dict) -> str:
        """Execute a Kubernetes tool.

        Args:
            tool_name: Name of the tool to execute
            tool_input: Input parameters for the tool

        Returns:
            Tool execution result as a string
        """
        # Map tool names to methods
        tool_map = {
            # K8s resource inspection tools
            "list_pods": self.k8s.list_pods,
            "get_pod_logs": self.k8s.get_pod_logs,
            "describe_pod": self.k8s.describe_pod,
            "list_deployments": self.k8s.list_deployments,
            "list_namespaces": self.k8s.list_namespaces,
            # K8s resource management tools
            "scale_deployment": self.k8s.scale_deployment,
            "apply_manifest": self.k8s.apply_manifest,
            "delete_resource": self.k8s.delete_resource,
            "get_resource": self.k8s.get_resource,
            # Testing tools
            "http_request": self.testing.http_request,
            "exec_in_pod": self.testing.exec_in_pod,
            "wait_for_pod_ready": self.testing.wait_for_pod_ready,
            "check_service_endpoints": self.testing.check_service_endpoints,
        }

        if tool_name not in tool_map:
            raise ValueError(f"Unknown tool: {tool_name}")

        tool_func = tool_map[tool_name]
        return tool_func(**tool_input)


def main():
    """Main entry point for the agent."""
    # Get configuration from environment
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        logger.error("ANTHROPIC_API_KEY environment variable not set")
        return

    mission = os.environ.get("MISSION")
    if not mission:
        logger.error("MISSION environment variable not set")
        return

    # Detect if running in cluster
    in_cluster = os.environ.get("KUBERNETES_SERVICE_HOST") is not None
    logger.info(f"Running in cluster: {in_cluster}")

    # Create and run agent
    agent = DevoopsAgent(api_key=api_key, in_cluster=in_cluster)

    try:
        result = agent.execute_mission(mission)
        logger.info("=" * 80)
        logger.info("MISSION RESULT:")
        logger.info("=" * 80)
        logger.info(result)
        logger.info("=" * 80)
    except Exception as e:
        logger.error(f"Mission failed: {e}", exc_info=True)


if __name__ == "__main__":
    main()
