"""Main agent implementation for devoops."""

import os
import json
import logging
import threading
import time
from datetime import datetime
from enum import Enum
from typing import Optional, Dict, List
from openai import OpenAI
from devoops.k8s_tools import K8sClient, TOOLS
from devoops.test_tools import TestingClient, TESTING_TOOLS

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)


class MissionStatus(str, Enum):
    """Status of a mission."""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class Mission:
    """Represents a mission with status and results."""

    def __init__(self, mission_id: str, prompt: str):
        self.id = mission_id
        self.prompt = prompt
        self.status = MissionStatus.PENDING
        self.logs: List[str] = []
        self.result: Optional[str] = None
        self.created_at = datetime.utcnow()
        self.started_at: Optional[datetime] = None
        self.completed_at: Optional[datetime] = None
        self.error: Optional[str] = None

    def add_log(self, message: str):
        """Add a log entry with timestamp."""
        timestamp = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
        log_entry = f"[{timestamp}] {message}"
        self.logs.append(log_entry)
        logger.info(message)

    def to_dict(self):
        """Convert mission to dictionary for API responses."""
        return {
            "id": self.id,
            "prompt": self.prompt,
            "status": self.status.value,
            "logs": self.logs,
            "result": self.result,
            "error": self.error,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
        }


class DevoopsAgent:
    """The Devoops agent that executes missions in Kubernetes."""

    def __init__(self, api_key: str, in_cluster: bool = False):
        """Initialize the agent.

        Args:
            api_key: OpenAI API key
            in_cluster: Whether running in-cluster (use ServiceAccount) or local
        """
        self.client = OpenAI(api_key=api_key)
        self.k8s = K8sClient(in_cluster=in_cluster)
        self.testing = TestingClient(core_v1=self.k8s.core_v1)
        self.model = "gpt-4o"

        # Tools are already in OpenAI format
        self.tools = TOOLS + TESTING_TOOLS

        # Mission storage (in-memory)
        self.missions: Dict[str, Mission] = {}
        self.mission_counter = 0
        self.lock = threading.Lock()
        self.worker_thread: Optional[threading.Thread] = None
        self.running = False

        # System prompt to encourage testing
        self.system_prompt = """You are a DevOps agent with the ability to manage Kubernetes resources and test your changes.

IMPORTANT: After making changes (creating/updating resources), you should verify they work correctly:
1. Use wait_for_pod_ready to ensure pods are running before testing
2. Use check_service_endpoints to verify services have backing pods
3. Use http_request to test HTTP endpoints
4. Use exec_in_pod to run commands inside pods for verification

Always test your changes when possible to ensure the mission succeeded."""

    def submit_mission(self, prompt: str) -> str:
        """Submit a new mission and return its ID.

        Args:
            prompt: The mission prompt

        Returns:
            Mission ID
        """
        with self.lock:
            self.mission_counter += 1
            mission_id = f"mission-{self.mission_counter}"
            mission = Mission(mission_id, prompt)
            self.missions[mission_id] = mission
            mission.add_log(f"Mission submitted: {prompt}")

        return mission_id

    def get_mission(self, mission_id: str) -> Optional[Mission]:
        """Get a mission by ID.

        Args:
            mission_id: The mission ID

        Returns:
            Mission object or None
        """
        return self.missions.get(mission_id)

    def list_missions(self) -> List[Mission]:
        """List all missions.

        Returns:
            List of Mission objects
        """
        return list(self.missions.values())

    def start_worker(self):
        """Start the background worker thread to process missions."""
        if self.worker_thread is not None and self.worker_thread.is_alive():
            logger.warning("Worker thread already running")
            return

        self.running = True
        self.worker_thread = threading.Thread(target=self._worker_loop, daemon=True)
        self.worker_thread.start()
        logger.info("Mission worker thread started")

    def stop_worker(self):
        """Stop the background worker thread."""
        self.running = False
        if self.worker_thread:
            self.worker_thread.join(timeout=5)
        logger.info("Mission worker thread stopped")

    def _worker_loop(self):
        """Background worker that processes pending missions."""
        logger.info("Worker loop started")
        while self.running:
            # Find next pending mission
            pending_mission = None
            with self.lock:
                for mission in self.missions.values():
                    if mission.status == MissionStatus.PENDING:
                        pending_mission = mission
                        mission.status = MissionStatus.RUNNING
                        mission.started_at = datetime.utcnow()
                        break

            if pending_mission:
                try:
                    pending_mission.add_log("Starting mission execution")
                    result = self._execute_mission_internal(pending_mission)
                    pending_mission.result = result
                    pending_mission.status = MissionStatus.COMPLETED
                    pending_mission.completed_at = datetime.utcnow()
                    pending_mission.add_log("Mission completed successfully")
                except Exception as e:
                    error_msg = str(e)
                    pending_mission.error = error_msg
                    pending_mission.status = MissionStatus.FAILED
                    pending_mission.completed_at = datetime.utcnow()
                    pending_mission.add_log(f"Mission failed: {error_msg}")
                    logger.error(f"Mission {pending_mission.id} failed", exc_info=True)
            else:
                # No pending missions, sleep briefly
                time.sleep(1)

        logger.info("Worker loop exited")

    def _execute_mission_internal(self, mission: Mission) -> str:
        """Execute a mission (internal method called by worker).

        Args:
            mission: The mission to execute

        Returns:
            The final response from the agent
        """
        messages = [
            {"role": "system", "content": self.system_prompt},
            {"role": "user", "content": mission.prompt}
        ]

        # Agentic loop
        while True:
            response = self.client.chat.completions.create(
                model=self.model,
                max_tokens=4096,
                tools=self.tools,
                messages=messages,
            )

            message = response.choices[0].message
            finish_reason = response.choices[0].finish_reason

            mission.add_log(f"Finish reason: {finish_reason}")

            # Add assistant response to conversation
            messages.append(message)

            # Check if we're done
            if finish_reason == "stop":
                # Return the final text response
                return message.content or ""

            # Process tool calls
            if finish_reason == "tool_calls" and message.tool_calls:
                tool_messages = []

                for tool_call in message.tool_calls:
                    tool_name = tool_call.function.name
                    tool_input = json.loads(tool_call.function.arguments)

                    mission.add_log(f"Executing tool: {tool_name}")

                    # Execute the tool
                    try:
                        result = self._execute_tool(tool_name, tool_input)
                        result_preview = result[:200] if len(result) > 200 else result
                        mission.add_log(f"Tool result: {result_preview}...")

                        tool_messages.append({
                            "role": "tool",
                            "tool_call_id": tool_call.id,
                            "content": result,
                        })
                    except Exception as e:
                        error_msg = f"Error executing tool: {str(e)}"
                        mission.add_log(error_msg)
                        tool_messages.append({
                            "role": "tool",
                            "tool_call_id": tool_call.id,
                            "content": error_msg,
                        })

                # Add tool results to conversation
                messages.extend(tool_messages)

            else:
                # Unexpected finish reason
                mission.add_log(f"Unexpected finish reason: {finish_reason}")
                return "Mission ended unexpectedly"

    def execute_mission(self, mission: str) -> str:
        """Execute a mission using OpenAI and Kubernetes tools.

        Args:
            mission: The mission prompt describing what to do

        Returns:
            The final response from the agent
        """
        logger.info(f"Starting mission: {mission}")

        messages = [
            {"role": "system", "content": self.system_prompt},
            {"role": "user", "content": mission}
        ]

        # Agentic loop
        while True:
            response = self.client.chat.completions.create(
                model=self.model,
                max_tokens=4096,
                tools=self.tools,  # Use converted tools
                messages=messages,
            )

            message = response.choices[0].message
            finish_reason = response.choices[0].finish_reason

            logger.info(f"Finish reason: {finish_reason}")

            # Add assistant response to conversation
            messages.append(message)

            # Check if we're done
            if finish_reason == "stop":
                # Return the final text response
                logger.info("Mission completed")
                return message.content or ""

            # Process tool calls
            if finish_reason == "tool_calls" and message.tool_calls:
                tool_messages = []

                for tool_call in message.tool_calls:
                    tool_name = tool_call.function.name
                    tool_input = json.loads(tool_call.function.arguments)

                    logger.info(f"Executing tool: {tool_name} with input: {tool_input}")

                    # Execute the tool
                    try:
                        result = self._execute_tool(tool_name, tool_input)
                        logger.info(f"Tool result: {result[:200]}...")  # Log first 200 chars

                        tool_messages.append({
                            "role": "tool",
                            "tool_call_id": tool_call.id,
                            "content": result,
                        })
                    except Exception as e:
                        logger.error(f"Tool execution error: {e}")
                        tool_messages.append({
                            "role": "tool",
                            "tool_call_id": tool_call.id,
                            "content": f"Error executing tool: {str(e)}",
                        })

                # Add tool results to conversation
                messages.extend(tool_messages)

            else:
                # Unexpected finish reason
                logger.warning(f"Unexpected finish reason: {finish_reason}")
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


def create_flask_app(agent: DevoopsAgent):
    """Create Flask app with API endpoints for the agent.

    Args:
        agent: The DevoopsAgent instance

    Returns:
        Flask application
    """
    from flask import Flask, jsonify, request

    app = Flask(__name__)

    @app.route("/health")
    def health():
        """Health check endpoint."""
        return jsonify({"status": "healthy"}), 200

    @app.route("/api/missions", methods=["POST"])
    def submit_mission():
        """Submit a new mission."""
        data = request.get_json()
        if not data or "prompt" not in data:
            return jsonify({"error": "Missing 'prompt' field"}), 400

        mission_id = agent.submit_mission(data["prompt"])
        mission = agent.get_mission(mission_id)

        return jsonify(mission.to_dict()), 201

    @app.route("/api/missions", methods=["GET"])
    def list_missions():
        """List all missions."""
        missions = agent.list_missions()
        return jsonify([m.to_dict() for m in missions]), 200

    @app.route("/api/missions/<mission_id>", methods=["GET"])
    def get_mission(mission_id):
        """Get a specific mission."""
        mission = agent.get_mission(mission_id)
        if not mission:
            return jsonify({"error": "Mission not found"}), 404

        return jsonify(mission.to_dict()), 200

    return app


def main():
    """Main entry point for the agent."""
    # Get configuration from environment
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        logger.error("OPENAI_API_KEY environment variable not set")
        return

    # Detect if running in cluster
    in_cluster = os.environ.get("KUBERNETES_SERVICE_HOST") is not None
    logger.info(f"Running in cluster: {in_cluster}")

    # Create agent
    agent = DevoopsAgent(api_key=api_key, in_cluster=in_cluster)

    # Check if running in server mode or CLI mode
    mode = os.environ.get("MODE", "cli")

    if mode == "server":
        # Start background worker
        agent.start_worker()

        # Run Flask server
        logger.info("Starting agent in server mode")
        app = create_flask_app(agent)
        port = int(os.environ.get("PORT", 5000))
        app.run(host="0.0.0.0", port=port, debug=False)
    else:
        # CLI mode - execute single mission from env var
        mission = os.environ.get("MISSION")
        if not mission:
            logger.error("MISSION environment variable not set")
            return

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
