"""
Demo API Service - OAuth2 Token Validation

This service demonstrates how to validate OAuth2 access tokens from Keycloak
and respond with user information. The agent will call these endpoints using
delegated user tokens.
"""

import os
import logging
from functools import wraps
from flask import Flask, jsonify, request
from jose import jwt, JWTError
import requests

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)

# Configuration
KEYCLOAK_URL = os.getenv("KEYCLOAK_URL", "http://keycloak:8080")  # For fetching public keys
KEYCLOAK_PUBLIC_URL = os.getenv("KEYCLOAK_PUBLIC_URL", "http://localhost:30080")  # Expected issuer in tokens
KEYCLOAK_REALM = os.getenv("KEYCLOAK_REALM", "agent-demo")
ISSUER = f"{KEYCLOAK_PUBLIC_URL}/realms/{KEYCLOAK_REALM}"  # Must match token issuer

# Cache for public keys
_public_keys = None


def get_public_keys():
    """Fetch Keycloak's public keys for token verification."""
    global _public_keys
    if _public_keys is None:
        try:
            # Use internal Keycloak URL to fetch keys (pod-to-pod communication)
            jwks_url = f"{KEYCLOAK_URL}/realms/{KEYCLOAK_REALM}/protocol/openid-connect/certs"
            logger.info(f"Fetching public keys from: {jwks_url}")
            response = requests.get(jwks_url, timeout=10)
            response.raise_for_status()
            _public_keys = response.json()
            logger.info("Successfully fetched public keys")
        except Exception as e:
            logger.error(f"Failed to fetch public keys: {e}")
            raise
    return _public_keys


def require_token(f):
    """Decorator to require and validate OAuth2 token."""
    @wraps(f)
    def decorated(*args, **kwargs):
        auth_header = request.headers.get("Authorization")

        if not auth_header or not auth_header.startswith("Bearer "):
            return jsonify({"error": "Missing or invalid Authorization header"}), 401

        token = auth_header.split(" ")[1]

        try:
            # Get public keys for verification
            jwks = get_public_keys()

            # Decode and verify the token
            unverified_header = jwt.get_unverified_header(token)
            rsa_key = None

            for key in jwks["keys"]:
                if key["kid"] == unverified_header["kid"]:
                    rsa_key = {
                        "kty": key["kty"],
                        "kid": key["kid"],
                        "use": key["use"],
                        "n": key["n"],
                        "e": key["e"]
                    }
                    break

            if rsa_key is None:
                return jsonify({"error": "Invalid token - key not found"}), 401

            # Verify and decode
            payload = jwt.decode(
                token,
                rsa_key,
                algorithms=["RS256"],
                audience="account",
                issuer=ISSUER
            )

            # Extract actor (agent) information from the 'act' claim if present
            act_claim = payload.get("act")
            actor_info = None
            if act_claim:
                actor_info = {
                    "sub": act_claim.get("sub"),
                    "note": "This request was made by an agent acting on behalf of the user"
                }
                logger.info(f"Token has 'act' claim - Actor: {actor_info['sub']}, Subject: {payload.get('preferred_username')}")

            # Add user info to request context
            request.user = {
                "username": payload.get("preferred_username"),
                "email": payload.get("email"),
                "sub": payload.get("sub"),
                "name": payload.get("name"),
                "scopes": payload.get("scope", "").split(),
                "actor": actor_info  # Include actor information if present
            }

            logger.info(f"Authenticated user: {request.user['username']}")

            return f(*args, **kwargs)

        except JWTError as e:
            logger.error(f"Token validation failed: {e}")
            return jsonify({"error": f"Invalid token: {str(e)}"}), 401
        except Exception as e:
            logger.error(f"Unexpected error: {e}")
            return jsonify({"error": "Internal server error"}), 500

    return decorated


@app.route("/health", methods=["GET"])
def health():
    """Health check endpoint."""
    return jsonify({"status": "healthy"}), 200


@app.route("/api/whoami", methods=["GET"])
@require_token
def whoami():
    """Return information about the authenticated user."""
    response = {
        "message": f"Hello, {request.user['username']}!",
        "user": request.user,
    }

    if request.user.get("actor"):
        response["note"] = "This request was made by an agent acting on your behalf"
    else:
        response["note"] = "This request was made using your delegated OAuth2 token"

    return jsonify(response), 200


@app.route("/api/tasks", methods=["GET"])
@require_token
def list_tasks():
    """Return a list of tasks for the authenticated user."""
    # This is dummy data - in a real system, this would be user-specific
    return jsonify({
        "user": request.user["username"],
        "tasks": [
            {"id": 1, "title": "Review pull request", "status": "pending"},
            {"id": 2, "title": "Deploy to staging", "status": "completed"},
            {"id": 3, "title": "Update documentation", "status": "in_progress"}
        ]
    }), 200


@app.route("/api/tasks", methods=["POST"])
@require_token
def create_task():
    """Create a new task for the authenticated user."""
    data = request.get_json()

    if not data or "title" not in data:
        return jsonify({"error": "Missing 'title' field"}), 400

    # This is dummy data - in a real system, this would persist the task
    task = {
        "id": 999,
        "title": data["title"],
        "status": "pending",
        "owner": request.user["username"]
    }

    logger.info(f"Created task for user {request.user['username']}: {task}")

    return jsonify({
        "message": "Task created successfully",
        "task": task
    }), 201


@app.route("/api/protected-action", methods=["POST"])
@require_token
def protected_action():
    """Perform a protected action on behalf of the user."""
    data = request.get_json() or {}
    action = data.get("action", "unknown")

    logger.info(f"User {request.user['username']} performed action: {action}")

    return jsonify({
        "message": f"Action '{action}' completed successfully",
        "performed_by": request.user["username"],
        "note": "This action was performed with your delegated permissions"
    }), 200


if __name__ == "__main__":
    logger.info(f"Starting demo service")
    logger.info(f"Keycloak URL: {KEYCLOAK_URL}")
    logger.info(f"Keycloak Realm: {KEYCLOAK_REALM}")
    logger.info(f"Issuer: {ISSUER}")

    app.run(host="0.0.0.0", port=5000, debug=False)
