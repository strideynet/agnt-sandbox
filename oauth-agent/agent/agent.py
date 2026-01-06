"""
OAuth Agent - Main agent logic

An agent that uses delegated OAuth2 tokens to act on behalf of users.
"""

import os
import logging
import time
from typing import Optional
from anthropic import Anthropic

from .oauth_client import OAuth2Client
from .tools import AgentTools

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class OAuthAgent:
    """An agent that operates with delegated user permissions via OAuth2."""

    def __init__(
        self,
        anthropic_api_key: str,
        oauth_client: OAuth2Client,
        tools: AgentTools
    ):
        """
        Initialize the OAuth agent.

        Args:
            anthropic_api_key: Anthropic API key for Claude
            oauth_client: OAuth2 client for managing tokens
            tools: Tools the agent can use
        """
        self.client = Anthropic(api_key=anthropic_api_key)
        self.oauth_client = oauth_client
        self.tools = tools
        self.model = "claude-3-7-sonnet-20250219"

    def execute_mission(self, mission: str, username: str) -> str:
        """
        Execute a mission on behalf of a user.

        Args:
            mission: The mission/task to accomplish
            username: The user on whose behalf to act

        Returns:
            Result of the mission
        """
        logger.info(f"Starting mission for user {username}: {mission}")

        # Check if we have delegation
        access_token = self.oauth_client.get_user_token(username)
        if not access_token:
            error_msg = f"No delegation found for user {username}. User must complete OAuth2 consent flow first."
            logger.error(error_msg)
            return error_msg

        logger.info(f"✓ Successfully obtained access token for {username}")

        # System prompt explaining the agent's context
        system_prompt = f"""You are an agent acting on behalf of user '{username}' with delegated OAuth2 permissions.

You have access to tools that use this user's access token to:
- Get user information
- List and create tasks
- Perform protected actions

Important context:
- You are operating with DELEGATED permissions - the user has explicitly granted you access
- All API calls you make will be authenticated as {username}
- Your actions are auditable and the user can revoke your access at any time
- Be responsible with these delegated permissions

Your mission: {mission}

Use the available tools to accomplish this mission on behalf of {username}."""

        # Execute the agent loop
        messages = [{"role": "user", "content": mission}]

        max_iterations = 10
        iteration = 0

        while iteration < max_iterations:
            iteration += 1
            logger.info(f"Agent iteration {iteration}/{max_iterations}")

            try:
                # Get token (might have been refreshed)
                access_token = self.oauth_client.get_user_token(username)
                if not access_token:
                    return "Lost delegation - user may have revoked access"

                # Call Claude
                response = self.client.messages.create(
                    model=self.model,
                    max_tokens=4096,
                    system=system_prompt,
                    tools=self.tools.get_tools_definition(),
                    messages=messages
                )

                logger.info(f"Claude response - stop_reason: {response.stop_reason}")

                # Add assistant response to messages
                messages.append({"role": "assistant", "content": response.content})

                # Check if we're done
                if response.stop_reason == "end_turn":
                    # Extract text response
                    text_content = [
                        block.text for block in response.content
                        if hasattr(block, 'text')
                    ]
                    result = "\n".join(text_content) if text_content else "Mission completed"
                    logger.info(f"Mission completed after {iteration} iterations")
                    return result

                # Process tool calls
                if response.stop_reason == "tool_use":
                    tool_results = []

                    for block in response.content:
                        if block.type == "tool_use":
                            logger.info(f"Executing tool: {block.name}")
                            logger.debug(f"Tool input: {block.input}")

                            # Execute the tool with the user's token
                            result = self.tools.execute_tool(
                                block.name,
                                block.input,
                                access_token
                            )

                            logger.info(f"Tool result: {result[:200]}...")

                            tool_results.append({
                                "type": "tool_result",
                                "tool_use_id": block.id,
                                "content": result
                            })

                    # Add tool results to messages
                    messages.append({"role": "user", "content": tool_results})

                else:
                    logger.warning(f"Unexpected stop_reason: {response.stop_reason}")
                    return f"Unexpected stop reason: {response.stop_reason}"

            except Exception as e:
                logger.error(f"Error during agent execution: {e}")
                return f"Error: {str(e)}"

        return f"Mission incomplete - reached maximum iterations ({max_iterations})"


def main():
    """Main entry point for the agent."""
    logger.info("=" * 60)
    logger.info("OAuth Agent Starting")
    logger.info("=" * 60)

    # Configuration
    anthropic_api_key = os.getenv("ANTHROPIC_API_KEY")
    if not anthropic_api_key:
        raise ValueError("ANTHROPIC_API_KEY environment variable is required")

    keycloak_url = os.getenv("KEYCLOAK_URL", "http://keycloak:8080")
    realm = os.getenv("KEYCLOAK_REALM", "agent-demo")
    client_id = os.getenv("CLIENT_ID", "oauth-agent")
    client_secret = os.getenv("CLIENT_SECRET")
    if not client_secret:
        raise ValueError("CLIENT_SECRET environment variable is required")

    # Agent client for token exchange
    exchange_client_id = os.getenv("EXCHANGE_CLIENT_ID", "oauth-agent-client")
    exchange_client_secret = os.getenv("EXCHANGE_CLIENT_SECRET")
    if not exchange_client_secret:
        raise ValueError("EXCHANGE_CLIENT_SECRET environment variable is required")

    consent_ui_url = os.getenv("CONSENT_UI_URL", "http://consent-ui:8080")
    demo_service_url = os.getenv("DEMO_SERVICE_URL", "http://demo-service:5000")

    # Mission configuration
    mission = os.getenv("MISSION")
    if not mission:
        raise ValueError("MISSION environment variable is required")

    username = os.getenv("USERNAME")
    if not username:
        raise ValueError("USERNAME environment variable is required")

    # Display configuration
    logger.info("Configuration:")
    logger.info(f"  Keycloak: {keycloak_url}")
    logger.info(f"  Realm: {realm}")
    logger.info(f"  Consent UI Client ID: {client_id}")
    logger.info(f"  Agent Client ID: {exchange_client_id}")
    logger.info(f"  Consent UI: {consent_ui_url}")
    logger.info(f"  Demo Service: {demo_service_url}")
    logger.info(f"  Username: {username}")
    logger.info(f"  Mission: {mission}")
    logger.info("")

    # Initialize OAuth client
    token_endpoint = f"{keycloak_url}/realms/{realm}/protocol/openid-connect/token"
    oauth_client = OAuth2Client(
        token_endpoint=token_endpoint,
        client_id=client_id,
        client_secret=client_secret,
        consent_ui_url=consent_ui_url,
        exchange_client_id=exchange_client_id,
        exchange_client_secret=exchange_client_secret,
        audience="account"  # Use standard Keycloak account client
    )

    # Initialize tools
    tools = AgentTools(demo_service_url)

    # Initialize agent
    agent = OAuthAgent(
        anthropic_api_key=anthropic_api_key,
        oauth_client=oauth_client,
        tools=tools
    )

    # Wait a bit for services to be ready
    logger.info("Waiting 5 seconds for services to stabilize...")
    time.sleep(5)

    # Execute mission
    logger.info("")
    logger.info("=" * 60)
    logger.info("EXECUTING MISSION")
    logger.info("=" * 60)
    logger.info("")

    result = agent.execute_mission(mission, username)

    logger.info("")
    logger.info("=" * 60)
    logger.info("MISSION RESULT")
    logger.info("=" * 60)
    logger.info(result)
    logger.info("")
    logger.info("=" * 60)
    logger.info("Agent finished")
    logger.info("=" * 60)


if __name__ == "__main__":
    main()
