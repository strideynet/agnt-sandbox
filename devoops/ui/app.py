"""
Mission Control API Backend - Devoops Agent

This Flask application provides:
- OAuth2 authentication via Keycloak
- API proxy to the devoops agent
- Session management

The React frontend handles all UI rendering.
"""

import base64
import json as json_module
import logging
import os
import secrets
from functools import wraps
from urllib.parse import urlencode

import requests
from flask import Flask, jsonify, redirect, request, session

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)
app.secret_key = os.getenv("SESSION_SECRET", secrets.token_hex(32))

# Configuration
AGENT_URL = os.getenv("AGENT_URL", "http://devoops-agent:5000")

# Keycloak Configuration
KEYCLOAK_URL = os.getenv("KEYCLOAK_URL", "http://keycloak.keycloak.svc.cluster.local:8080")
KEYCLOAK_PUBLIC_URL = os.getenv("KEYCLOAK_PUBLIC_URL", KEYCLOAK_URL)
KEYCLOAK_REALM = os.getenv("KEYCLOAK_REALM", "devoops")
CLIENT_ID = os.getenv("CLIENT_ID", "devoops-ui-client")
CLIENT_SECRET = os.getenv("CLIENT_SECRET", "devoops-ui-secret-change-in-production")
REDIRECT_URI = os.getenv("REDIRECT_URI", "http://localhost:30901/callback")

# OAuth2 endpoints
AUTH_ENDPOINT = f"{KEYCLOAK_PUBLIC_URL}/realms/{KEYCLOAK_REALM}/protocol/openid-connect/auth"
TOKEN_ENDPOINT = f"{KEYCLOAK_URL}/realms/{KEYCLOAK_REALM}/protocol/openid-connect/token"
USERINFO_ENDPOINT = f"{KEYCLOAK_URL}/realms/{KEYCLOAK_REALM}/protocol/openid-connect/userinfo"
LOGOUT_ENDPOINT = f"{KEYCLOAK_PUBLIC_URL}/realms/{KEYCLOAK_REALM}/protocol/openid-connect/logout"


def login_required(f):
    """Decorator to require authentication for routes."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if "username" not in session:
            # For API routes, return 401 JSON response
            if request.path.startswith('/api/'):
                return jsonify({"error": "Unauthorized"}), 401
            # For other routes, redirect to login page
            return redirect("/login-page")
        return f(*args, **kwargs)
    return decorated_function


# =============================================================================
# API Routes (proxied to agent)
# =============================================================================

@app.route("/api/missions", methods=["GET", "POST"])
@login_required
def missions_proxy():
    """Proxy missions API to the agent."""
    try:
        if request.method == "POST":
            response = requests.post(
                f"{AGENT_URL}/api/missions",
                json=request.get_json(),
                timeout=10
            )
        else:
            response = requests.get(f"{AGENT_URL}/api/missions", timeout=10)

        return response.json(), response.status_code
    except Exception as e:
        logger.error(f"Failed to proxy request to agent: {e}")
        return jsonify({"error": str(e)}), 500


@app.route("/api/missions/<mission_id>", methods=["GET"])
@login_required
def mission_proxy(mission_id):
    """Proxy individual mission API to the agent."""
    try:
        response = requests.get(f"{AGENT_URL}/api/missions/{mission_id}", timeout=10)
        return response.json(), response.status_code
    except Exception as e:
        logger.error(f"Failed to proxy mission request to agent: {e}")
        return jsonify({"error": str(e)}), 500


@app.route("/api/me")
@login_required
def get_current_user():
    """Return current user information including token claims."""
    user_info = {
        "username": session.get("username"),
        "email": session.get("email"),
    }

    # Decode the access token to expose claims
    access_token = session.get("access_token")
    if access_token:
        try:
            parts = access_token.split('.')
            if len(parts) == 3:
                # Decode header
                header_payload = parts[0]
                header_payload += '=' * (4 - len(header_payload) % 4)
                header = json_module.loads(base64.urlsafe_b64decode(header_payload))

                # Decode payload
                payload = parts[1]
                payload += '=' * (4 - len(payload) % 4)
                claims = json_module.loads(base64.urlsafe_b64decode(payload))

                user_info["token"] = {
                    "header": header,
                    "claims": claims,
                    "raw": access_token,
                }
        except Exception as e:
            logger.warning(f"Could not decode token: {e}")
            user_info["token"] = {"error": str(e), "raw": access_token}

    return jsonify(user_info), 200


# =============================================================================
# OAuth2 Authentication Routes
# =============================================================================

@app.route("/login")
def login():
    """Initiate OAuth2 authorization code flow."""
    # Generate random state for CSRF protection
    state = secrets.token_urlsafe(32)
    session["oauth_state"] = state

    # Build authorization URL
    params = {
        "client_id": CLIENT_ID,
        "response_type": "code",
        "scope": "openid profile email",
        "redirect_uri": REDIRECT_URI,
        "state": state
    }

    auth_url = f"{AUTH_ENDPOINT}?{urlencode(params)}"
    logger.info("Redirecting to Keycloak for authentication")

    return redirect(auth_url)


@app.route("/callback")
def callback():
    """Handle OAuth2 callback with authorization code."""
    # Verify state to prevent CSRF
    state = request.args.get("state")
    if state != session.get("oauth_state"):
        return jsonify({"error": "Invalid state parameter"}), 400

    # Get authorization code
    code = request.args.get("code")
    if not code:
        error = request.args.get("error", "unknown_error")
        error_desc = request.args.get("error_description", "No description")
        return jsonify({"error": f"{error}: {error_desc}"}), 400

    # Exchange code for tokens
    token_data = {
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": REDIRECT_URI,
        "client_id": CLIENT_ID,
        "client_secret": CLIENT_SECRET
    }

    try:
        logger.info("Exchanging authorization code for tokens...")
        token_response = requests.post(TOKEN_ENDPOINT, data=token_data, timeout=10)
        token_response.raise_for_status()
        tokens = token_response.json()

        logger.info("Token exchange successful")

        # Get user info
        userinfo_response = requests.get(
            USERINFO_ENDPOINT,
            headers={"Authorization": f"Bearer {tokens['access_token']}"},
            timeout=10
        )
        userinfo_response.raise_for_status()
        user_info = userinfo_response.json()

        # Store in session
        session["username"] = user_info.get("preferred_username")
        session["email"] = user_info.get("email")
        session["access_token"] = tokens["access_token"]

        logger.info(f"User logged in: {session['username']}")

        # Redirect to React app home
        return redirect("/")

    except Exception as e:
        logger.error(f"Error during OAuth2 flow: {e}")
        return jsonify({"error": f"Authentication error: {str(e)}"}), 500


@app.route("/logout")
def logout():
    """Clear session and redirect to Keycloak logout."""
    username = session.get("username")
    session.clear()

    logger.info(f"User logged out: {username}")

    # Redirect to Keycloak logout, then back to the app
    redirect_url = request.url_root
    logout_url = f"{LOGOUT_ENDPOINT}?redirect_uri={redirect_url}"

    return redirect(logout_url)


# =============================================================================
# Health Check
# =============================================================================

@app.route("/health")
def health():
    """Health check endpoint."""
    return jsonify({"status": "healthy"}), 200


# =============================================================================
# Main
# =============================================================================

if __name__ == "__main__":
    logger.info("Starting Mission Control API Backend")
    logger.info(f"Agent URL: {AGENT_URL}")
    logger.info(f"Keycloak URL: {KEYCLOAK_URL}")
    logger.info(f"Keycloak Realm: {KEYCLOAK_REALM}")
    logger.info(f"Client ID: {CLIENT_ID}")
    logger.info(f"Redirect URI: {REDIRECT_URI}")

    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port, debug=False)
