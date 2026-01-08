"""Main agent implementation for devoops."""

import os
import json
import logging
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional, Dict, List, Any
from openai import OpenAI
from devoops.k8s_tools import K8sClient, READ_ONLY_TOOLS, MUTATING_TOOLS
from devoops.test_tools import TestingClient, READ_ONLY_TESTING_TOOLS, MUTATING_TESTING_TOOLS

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)


class MissionStatus(str, Enum):
    """Status of a mission."""
    PENDING = "pending"
    RUNNING = "running"
    AWAITING_CLARIFICATION = "awaiting_clarification"
    AWAITING_APPROVAL = "awaiting_approval"
    COMPLETED = "completed"
    FAILED = "failed"


class InteractionType(str, Enum):
    """Type of user interaction required."""
    CLARIFICATION = "clarification"
    PLAN_APPROVAL = "plan_approval"


@dataclass
class PlannedAction:
    """A single planned mutating action."""
    tool_name: str
    description: str
    parameters: dict
    risk_level: str = "medium"  # low, medium, high

    def to_dict(self) -> dict:
        return {
            "tool_name": self.tool_name,
            "description": self.description,
            "parameters": self.parameters,
            "risk_level": self.risk_level,
        }


@dataclass
class PendingInteraction:
    """Represents a pending interaction requiring user input."""
    interaction_type: InteractionType
    message: str
    planned_actions: List[PlannedAction] = field(default_factory=list)
    created_at: datetime = field(default_factory=datetime.utcnow)

    def to_dict(self) -> dict:
        return {
            "interaction_type": self.interaction_type.value,
            "message": self.message,
            "planned_actions": [a.to_dict() for a in self.planned_actions],
            "created_at": self.created_at.isoformat(),
        }


# Interaction tools for human-in-the-loop
INTERACTION_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "request_clarification",
            "description": "Request clarification from the user when the mission is ambiguous or you need more information. Use sparingly - try to be autonomous when possible.",
            "parameters": {
                "type": "object",
                "properties": {
                    "question": {
                        "type": "string",
                        "description": "The clarifying question to ask the user"
                    }
                },
                "required": ["question"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "propose_mutation_plan",
            "description": "Propose a plan of mutating actions for user approval. MUST be called before executing any mutating operations (scale_deployment, apply_manifest, delete_resource, exec_in_pod). Batch multiple related actions into a single plan. IMPORTANT: You must include the COMPLETE parameters for each action, including full YAML manifests for apply_manifest.",
            "parameters": {
                "type": "object",
                "properties": {
                    "summary": {
                        "type": "string",
                        "description": "Brief summary of what the plan will accomplish"
                    },
                    "actions": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "tool": {
                                    "type": "string",
                                    "description": "The tool to execute (scale_deployment, apply_manifest, delete_resource, exec_in_pod)"
                                },
                                "description": {
                                    "type": "string",
                                    "description": "Human-readable description of this action"
                                },
                                "parameters": {
                                    "type": "object",
                                    "description": "The COMPLETE parameters to pass to the tool. For apply_manifest, include the full yaml_content. For scale_deployment, include name, replicas, namespace. These exact parameters will be used when executing the action."
                                }
                            },
                            "required": ["tool", "description", "parameters"]
                        },
                        "description": "List of actions in the plan with their complete parameters"
                    }
                },
                "required": ["summary", "actions"]
            }
        }
    }
]


class Mission:
    """Represents a mission with status and results."""

    def __init__(self, mission_id: str, prompt: str, triggered_by: str = None):
        self.id = mission_id
        self.prompt = prompt
        self.triggered_by = triggered_by  # User email for audit trail
        self.status = MissionStatus.PENDING
        self.logs: List[str] = []
        self.result: Optional[str] = None
        self.created_at = datetime.utcnow()
        self.started_at: Optional[datetime] = None
        self.completed_at: Optional[datetime] = None
        self.error: Optional[str] = None

        # Human-in-the-loop fields
        self.pending_interaction: Optional[PendingInteraction] = None
        self.conversation_history: List[dict] = []
        self.plan_approved: bool = False
        self._pending_tool_call_id: Optional[str] = None
        self._resume_flag: bool = False

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
            "triggered_by": self.triggered_by,
            "status": self.status.value,
            "logs": self.logs,
            "result": self.result,
            "error": self.error,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "pending_interaction": self.pending_interaction.to_dict() if self.pending_interaction else None,
            "plan_approved": self.plan_approved,
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
        self.in_cluster = in_cluster
        # Default K8s client (without impersonation) for non-mission operations
        self.k8s = K8sClient(in_cluster=in_cluster)
        self.testing = TestingClient(core_v1=self.k8s.core_v1)
        self.model = "gpt-4o"

        # Tool sets for human-in-the-loop
        self.read_only_tools = READ_ONLY_TOOLS + READ_ONLY_TESTING_TOOLS + INTERACTION_TOOLS
        self.mutating_tools = MUTATING_TOOLS + MUTATING_TESTING_TOOLS
        self.all_tools = self.read_only_tools + self.mutating_tools

        # Mutating tool names for validation
        self.mutating_tool_names = {
            "scale_deployment", "apply_manifest", "delete_resource", "exec_in_pod"
        }

        # Mission storage (in-memory)
        self.missions: Dict[str, Mission] = {}
        self.mission_counter = 0
        self.lock = threading.Lock()
        self.worker_thread: Optional[threading.Thread] = None
        self.running = False

    def submit_mission(self, prompt: str, triggered_by: str = None) -> str:
        """Submit a new mission and return its ID.

        Args:
            prompt: The mission prompt
            triggered_by: Email of the user who triggered the mission (for audit trail)

        Returns:
            Mission ID
        """
        with self.lock:
            self.mission_counter += 1
            mission_id = f"mission-{self.mission_counter}"
            mission = Mission(mission_id, prompt, triggered_by=triggered_by)
            self.missions[mission_id] = mission
            mission.add_log(f"Mission submitted by {triggered_by or 'unknown'}: {prompt}")

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
            # Find next pending mission or one that needs to resume
            active_mission = None
            with self.lock:
                for mission in self.missions.values():
                    if mission.status == MissionStatus.PENDING:
                        active_mission = mission
                        mission.status = MissionStatus.RUNNING
                        mission.started_at = datetime.utcnow()
                        break
                    # Resume missions that were waiting and got a response
                    elif mission._resume_flag:
                        active_mission = mission
                        mission._resume_flag = False
                        mission.status = MissionStatus.RUNNING
                        break

            if active_mission:
                try:
                    active_mission.add_log("Executing mission")
                    result = self._execute_mission_internal(active_mission)

                    if result is None:
                        # Mission paused for user interaction, don't mark as complete
                        active_mission.add_log("Mission paused awaiting user input")
                        continue

                    active_mission.result = result
                    active_mission.status = MissionStatus.COMPLETED
                    active_mission.completed_at = datetime.utcnow()
                    active_mission.add_log("Mission completed successfully")
                except Exception as e:
                    error_msg = str(e)
                    active_mission.error = error_msg
                    active_mission.status = MissionStatus.FAILED
                    active_mission.completed_at = datetime.utcnow()
                    active_mission.add_log(f"Mission failed: {error_msg}")
                    logger.error(f"Mission {active_mission.id} failed", exc_info=True)
            else:
                # No pending missions, sleep briefly
                time.sleep(1)

        logger.info("Worker loop exited")

    def _get_system_prompt(self, mission: Mission) -> str:
        """Get the system prompt based on mission state."""
        base_prompt = """You are a DevOps agent with the ability to manage Kubernetes resources and test your changes.

IMPORTANT GUIDELINES:

1. AUTONOMY: Complete missions autonomously using sensible defaults. Use the 'default' namespace unless specified otherwise. Do NOT ask questions about namespace choices or other details that have reasonable defaults - just proceed with the default and let the user know what you chose.

2. MUTATION APPROVAL: Before executing ANY mutating operation (scale_deployment, apply_manifest, delete_resource, exec_in_pod), you MUST call propose_mutation_plan with a summary and list of actions. Wait for user approval before proceeding.

3. COMPLETE PARAMETERS IN PLANS: When calling propose_mutation_plan, you MUST include the COMPLETE parameters for each action. For apply_manifest, this means including the full YAML manifest in the yaml_content field. The user needs to see exactly what will be applied. Example:
   {
     "tool": "apply_manifest",
     "description": "Create nginx Deployment",
     "parameters": {
       "yaml_content": "apiVersion: apps/v1\\nkind: Deployment\\nmetadata:\\n  name: nginx\\n...",
       "namespace": "default"
     }
   }

4. BATCHING: Batch related mutating actions into a single plan when possible. For example, if deploying an application, include all manifests (Deployment, Service, ConfigMap) in one plan.

5. VERIFICATION: After making changes, verify they work correctly:
   - Use wait_for_pod_ready to ensure pods are running
   - Use check_service_endpoints to verify services
   - Use http_request to test HTTP endpoints

6. READ OPERATIONS: You can freely use read-only tools (list_pods, get_pod_logs, describe_pod, list_deployments, list_namespaces, get_resource, http_request, wait_for_pod_ready, check_service_endpoints) without approval.

7. CLARIFICATION: If you genuinely need user input (e.g., the mission is truly ambiguous with no reasonable default), use the request_clarification tool. NEVER ask questions in your final response text - either use request_clarification tool or proceed with a sensible default."""

        if mission.plan_approved:
            base_prompt += "\n\nNOTE: Your mutation plan has been APPROVED. You may now execute the planned actions."

        return base_prompt

    def _assess_risk(self, tool_name: str, parameters: dict) -> str:
        """Assess risk level of an action."""
        if tool_name == "delete_resource":
            return "high"
        if tool_name == "apply_manifest":
            return "medium"
        if tool_name == "scale_deployment":
            replicas = parameters.get("replicas", 1)
            return "high" if replicas == 0 else "low"
        if tool_name == "exec_in_pod":
            return "medium"
        return "medium"

    def _execute_mission_internal(self, mission: Mission) -> Optional[str]:
        """Execute a mission with human-in-the-loop support.

        Args:
            mission: The mission to execute

        Returns:
            The final response from the agent, or None if awaiting user input
        """
        # Create mission-specific K8s client with user impersonation for audit trail
        mission_k8s = K8sClient(
            in_cluster=self.in_cluster,
            impersonate_user=mission.triggered_by
        )
        mission_testing = TestingClient(core_v1=mission_k8s.core_v1)

        # Resume from stored conversation or start fresh
        if mission.conversation_history:
            messages = mission.conversation_history
        else:
            messages = [
                {"role": "system", "content": self._get_system_prompt(mission)},
                {"role": "user", "content": mission.prompt}
            ]

        # Agentic loop
        while True:
            # Select tools based on approval state
            tools = self.all_tools if mission.plan_approved else self.read_only_tools

            response = self.client.chat.completions.create(
                model=self.model,
                max_tokens=4096,
                tools=tools,
                messages=messages,
            )

            message = response.choices[0].message
            finish_reason = response.choices[0].finish_reason

            mission.add_log(f"Finish reason: {finish_reason}")

            # Add assistant response to conversation
            messages.append(message)
            mission.conversation_history = messages

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

                    mission.add_log(f"Tool call: {tool_name}")

                    # Handle interaction tools specially
                    if tool_name == "request_clarification":
                        question = tool_input.get("question", "")
                        mission.pending_interaction = PendingInteraction(
                            interaction_type=InteractionType.CLARIFICATION,
                            message=question,
                            planned_actions=[]
                        )
                        mission.status = MissionStatus.AWAITING_CLARIFICATION
                        mission._pending_tool_call_id = tool_call.id
                        mission.add_log(f"Requesting clarification: {question}")
                        return None  # Pause execution

                    if tool_name == "propose_mutation_plan":
                        summary = tool_input.get("summary", "")
                        actions = tool_input.get("actions", [])
                        planned_actions = [
                            PlannedAction(
                                tool_name=a.get("tool", ""),
                                description=a.get("description", ""),
                                parameters=a.get("parameters", {}),
                                risk_level=self._assess_risk(a.get("tool", ""), a.get("parameters", {}))
                            )
                            for a in actions
                        ]
                        mission.pending_interaction = PendingInteraction(
                            interaction_type=InteractionType.PLAN_APPROVAL,
                            message=summary,
                            planned_actions=planned_actions
                        )
                        mission.status = MissionStatus.AWAITING_APPROVAL
                        mission._pending_tool_call_id = tool_call.id
                        mission.add_log(f"Proposing plan: {summary}")
                        return None  # Pause execution

                    # Safety check: reject mutating tools if not approved
                    if tool_name in self.mutating_tool_names and not mission.plan_approved:
                        result = json.dumps({
                            "error": "Mutating operations require user approval. Use propose_mutation_plan first."
                        })
                        mission.add_log(f"Blocked unapproved mutation: {tool_name}")
                    else:
                        # Execute the tool using mission-specific clients
                        try:
                            result = self._execute_tool(
                                tool_name, tool_input,
                                k8s_client=mission_k8s,
                                testing_client=mission_testing
                            )
                            result_preview = result[:200] if len(result) > 200 else result
                            mission.add_log(f"Tool result: {result_preview}...")
                        except Exception as e:
                            result = f"Error executing tool: {str(e)}"
                            mission.add_log(result)

                    tool_messages.append({
                        "role": "tool",
                        "tool_call_id": tool_call.id,
                        "content": result,
                    })

                # Add tool results to conversation
                messages.extend(tool_messages)
                mission.conversation_history = messages

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

    def _execute_tool(
        self,
        tool_name: str,
        tool_input: dict,
        k8s_client: K8sClient = None,
        testing_client: TestingClient = None
    ) -> str:
        """Execute a Kubernetes tool.

        Args:
            tool_name: Name of the tool to execute
            tool_input: Input parameters for the tool
            k8s_client: K8s client to use (defaults to self.k8s)
            testing_client: Testing client to use (defaults to self.testing)

        Returns:
            Tool execution result as a string
        """
        # Use provided clients or fall back to defaults
        k8s = k8s_client or self.k8s
        testing = testing_client or self.testing

        # Map tool names to methods
        tool_map = {
            # K8s resource inspection tools
            "list_pods": k8s.list_pods,
            "get_pod_logs": k8s.get_pod_logs,
            "describe_pod": k8s.describe_pod,
            "list_deployments": k8s.list_deployments,
            "list_namespaces": k8s.list_namespaces,
            # K8s resource management tools
            "scale_deployment": k8s.scale_deployment,
            "apply_manifest": k8s.apply_manifest,
            "delete_resource": k8s.delete_resource,
            "get_resource": k8s.get_resource,
            # Testing tools
            "http_request": testing.http_request,
            "exec_in_pod": testing.exec_in_pod,
            "wait_for_pod_ready": testing.wait_for_pod_ready,
            "check_service_endpoints": testing.check_service_endpoints,
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

        triggered_by = data.get("triggered_by")
        mission_id = agent.submit_mission(data["prompt"], triggered_by=triggered_by)
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

    @app.route("/api/missions/<mission_id>/respond", methods=["POST"])
    def respond_to_mission(mission_id):
        """Handle user response to clarification request."""
        mission = agent.get_mission(mission_id)
        if not mission:
            return jsonify({"error": "Mission not found"}), 404

        if mission.status != MissionStatus.AWAITING_CLARIFICATION:
            return jsonify({"error": "Mission is not awaiting clarification"}), 400

        data = request.get_json()
        if not data or "response" not in data:
            return jsonify({"error": "Missing 'response' field"}), 400

        user_response = data["response"]

        # Add user response to conversation as tool result
        messages = mission.conversation_history
        messages.append({
            "role": "tool",
            "tool_call_id": mission._pending_tool_call_id,
            "content": json.dumps({"user_response": user_response})
        })
        mission.conversation_history = messages

        # Clear pending interaction and trigger resume
        mission.pending_interaction = None
        mission._resume_flag = True
        mission.add_log(f"User responded: {user_response}")

        return jsonify(mission.to_dict()), 200

    @app.route("/api/missions/<mission_id>/approve", methods=["POST"])
    def approve_plan(mission_id):
        """Handle user approval/rejection of mutation plan."""
        mission = agent.get_mission(mission_id)
        if not mission:
            return jsonify({"error": "Mission not found"}), 404

        if mission.status != MissionStatus.AWAITING_APPROVAL:
            return jsonify({"error": "Mission is not awaiting approval"}), 400

        data = request.get_json()
        if not data or "approved" not in data:
            return jsonify({"error": "Missing 'approved' field"}), 400

        approved = data["approved"]
        messages = mission.conversation_history

        if approved:
            # Grant approval
            mission.plan_approved = True
            messages.append({
                "role": "tool",
                "tool_call_id": mission._pending_tool_call_id,
                "content": json.dumps({
                    "approved": True,
                    "message": "Plan approved. You may now execute the planned actions."
                })
            })
            mission.add_log("User APPROVED the mutation plan")
        else:
            # Rejection with reason
            rejection_reason = data.get("rejection_reason", "Plan rejected by user")
            messages.append({
                "role": "tool",
                "tool_call_id": mission._pending_tool_call_id,
                "content": json.dumps({
                    "approved": False,
                    "message": f"Plan rejected: {rejection_reason}"
                })
            })
            mission.add_log(f"User REJECTED the plan: {rejection_reason}")

        mission.conversation_history = messages
        mission.pending_interaction = None
        mission._resume_flag = True

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
