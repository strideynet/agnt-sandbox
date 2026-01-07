"""
Consent UI - OAuth2 Authorization Flow

This web application allows users to grant the agent permission to act on their behalf.
It implements the OAuth2 authorization code flow with Keycloak.
"""

import os
import logging
import secrets
import json
from urllib.parse import urlencode
from flask import Flask, render_template_string, request, redirect, session, jsonify
import requests

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)
app.secret_key = os.getenv("SESSION_SECRET", secrets.token_hex(32))

# Configuration
KEYCLOAK_URL = os.getenv("KEYCLOAK_URL", "http://keycloak:8080")  # Internal cluster URL
KEYCLOAK_PUBLIC_URL = os.getenv("KEYCLOAK_PUBLIC_URL", KEYCLOAK_URL)  # Public URL for browser
KEYCLOAK_REALM = os.getenv("KEYCLOAK_REALM", "agent-demo")
CLIENT_ID = os.getenv("CLIENT_ID", "consent-ui-client")
CLIENT_SECRET = os.getenv("CLIENT_SECRET", "agent-secret-change-in-production")
REDIRECT_URI = os.getenv("REDIRECT_URI", "http://localhost:30800/callback")

# OAuth2 endpoints
# Both KEYCLOAK_URL and KEYCLOAK_PUBLIC_URL should point to the same Keycloak instance
# For Docker Desktop: KEYCLOAK_URL=host.docker.internal:30080, KEYCLOAK_PUBLIC_URL=localhost:30080
# This ensures token issuer matches validation URL (both resolve to host's NodePort service)
AUTH_ENDPOINT = f"{KEYCLOAK_PUBLIC_URL}/realms/{KEYCLOAK_REALM}/protocol/openid-connect/auth"
TOKEN_ENDPOINT = f"{KEYCLOAK_URL}/realms/{KEYCLOAK_REALM}/protocol/openid-connect/token"
USERINFO_ENDPOINT = f"{KEYCLOAK_URL}/realms/{KEYCLOAK_REALM}/protocol/openid-connect/userinfo"
LOGOUT_ENDPOINT = f"{KEYCLOAK_PUBLIC_URL}/realms/{KEYCLOAK_REALM}/protocol/openid-connect/logout"

# Token storage (in production, use a database)
# Format: {username: {"access_token": "...", "refresh_token": "...", "expires_at": timestamp}}
token_store = {}


# HTML Templates
HOME_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <title>OAuth Agent - Consent Manager</title>
    <style>
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
            max-width: 800px;
            margin: 50px auto;
            padding: 20px;
            background: #f5f5f5;
        }
        .container {
            background: white;
            padding: 40px;
            border-radius: 8px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        }
        h1 { color: #333; margin-bottom: 10px; }
        .subtitle { color: #666; margin-bottom: 30px; }
        .button {
            display: inline-block;
            padding: 12px 24px;
            background: #007bff;
            color: white;
            text-decoration: none;
            border-radius: 4px;
            border: none;
            cursor: pointer;
            font-size: 16px;
        }
        .button:hover { background: #0056b3; }
        .button.danger { background: #dc3545; }
        .button.danger:hover { background: #c82333; }
        .info-box {
            background: #e7f3ff;
            border-left: 4px solid #007bff;
            padding: 15px;
            margin: 20px 0;
        }
        .warning-box {
            background: #fff3cd;
            border-left: 4px solid #ffc107;
            padding: 15px;
            margin: 20px 0;
        }
        .status {
            margin: 20px 0;
            padding: 15px;
            border-radius: 4px;
        }
        .status.active {
            background: #d4edda;
            border: 1px solid #c3e6cb;
            color: #155724;
        }
        .status.inactive {
            background: #f8d7da;
            border: 1px solid #f5c6cb;
            color: #721c24;
        }
        pre {
            background: #f8f9fa;
            padding: 15px;
            border-radius: 4px;
            overflow-x: auto;
        }
        code { font-family: 'Monaco', 'Courier New', monospace; }
    </style>
</head>
<body>
    <div class="container">
        <h1>OAuth Agent Consent Manager</h1>
        <p class="subtitle">Delegate permissions to the agent</p>

        {% if user %}
        <div class="status active">
            <strong>✓ Active Delegation</strong><br>
            User: {{ user.username }}<br>
            Email: {{ user.email }}
        </div>

        <div class="warning-box">
            <strong>⚠️ What this means:</strong><br>
            The agent can now act on your behalf. It has access to your identity and can make
            API calls using your permissions. You can revoke this access at any time.
        </div>

        <p>
            <a href="/revoke" class="button danger">Revoke Agent Access</a>
            <a href="/test" class="button">Test Agent Token</a>
        </p>

        {% else %}
        <div class="status inactive">
            <strong>✗ No Active Delegation</strong><br>
            The agent does not have permission to act on your behalf.
        </div>

        <div class="info-box">
            <strong>What is this?</strong><br>
            This interface allows you to grant the OAuth Agent permission to act on your behalf.
            You'll be redirected to Keycloak to authenticate and consent to the delegation.
        </div>

        <p>
            <a href="/authorize" class="button">Grant Agent Access</a>
        </p>
        {% endif %}

        <hr style="margin: 40px 0;">

        <h2>About This Experiment</h2>
        <p>
            This is an experimental system exploring OAuth2-based user delegation for agents.
            The agent is a long-lived process that can perform actions on behalf of users who
            have explicitly granted it permission.
        </p>

        <h3>How it works:</h3>
        <ol>
            <li>You authenticate with Keycloak (identity provider)</li>
            <li>You consent to delegate your permissions to the agent</li>
            <li>The agent receives OAuth2 tokens (access + refresh)</li>
            <li>The agent uses these tokens to make API calls as you</li>
            <li>You can revoke access at any time</li>
        </ol>
    </div>
</body>
</html>
"""

SUCCESS_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <title>Success - OAuth Agent</title>
    <style>
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
            max-width: 800px;
            margin: 50px auto;
            padding: 20px;
            background: #f5f5f5;
        }
        .container {
            background: white;
            padding: 40px;
            border-radius: 8px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        }
        .success { color: #28a745; font-size: 48px; }
        .button {
            display: inline-block;
            padding: 12px 24px;
            background: #007bff;
            color: white;
            text-decoration: none;
            border-radius: 4px;
            margin-top: 20px;
        }
        pre {
            background: #f8f9fa;
            padding: 15px;
            border-radius: 4px;
            overflow-x: auto;
        }
    </style>
</head>
<body>
    <div class="container">
        <div class="success">✓</div>
        <h1>{{ title }}</h1>
        <p>{{ message }}</p>
        {% if user_info %}
        <h3>User Information:</h3>
        <pre>{{ user_info }}</pre>
        {% endif %}
        <a href="/" class="button">Return Home</a>
    </div>
</body>
</html>
"""


@app.route("/")
def home():
    """Home page showing delegation status."""
    user = None
    if "username" in session and session["username"] in token_store:
        user = {
            "username": session["username"],
            "email": session.get("email", "N/A")
        }

    return render_template_string(HOME_TEMPLATE, user=user)


@app.route("/authorize")
def authorize():
    """Initiate OAuth2 authorization code flow."""
    # Generate random state for CSRF protection
    state = secrets.token_urlsafe(32)
    session["oauth_state"] = state

    # Build authorization URL
    params = {
        "client_id": CLIENT_ID,
        "response_type": "code",
        "scope": "openid profile email offline_access",
        "redirect_uri": REDIRECT_URI,
        "state": state
    }

    auth_url = f"{AUTH_ENDPOINT}?{urlencode(params)}"
    logger.info(f"Redirecting to authorization URL: {auth_url}")

    return redirect(auth_url)


@app.route("/callback")
def callback():
    """Handle OAuth2 callback with authorization code."""
    # Verify state to prevent CSRF
    state = request.args.get("state")
    if state != session.get("oauth_state"):
        return "Invalid state parameter", 400

    # Get authorization code
    code = request.args.get("code")
    if not code:
        error = request.args.get("error", "unknown_error")
        error_desc = request.args.get("error_description", "No description")
        return f"Authorization failed: {error} - {error_desc}", 400

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
        logger.info(f"TOKEN_ENDPOINT: {TOKEN_ENDPOINT}")
        token_response = requests.post(TOKEN_ENDPOINT, data=token_data, timeout=10)
        token_response.raise_for_status()
        tokens = token_response.json()

        # Log token details for debugging
        logger.info(f"✓ Token exchange successful")
        logger.info(f"  Token type: {tokens.get('token_type')}")
        logger.info(f"  Expires in: {tokens.get('expires_in')} seconds")
        logger.info(f"  Scope: {tokens.get('scope')}")
        logger.info(f"  FULL ACCESS TOKEN: {tokens['access_token']}")
        if 'refresh_token' in tokens:
            logger.info(f"  FULL REFRESH TOKEN: {tokens.get('refresh_token')}")

        # Get user info
        logger.info("Fetching user information...")
        logger.info(f"USERINFO_ENDPOINT: {USERINFO_ENDPOINT}")
        logger.info(f"Full Authorization header: Bearer {tokens['access_token']}")
        userinfo_response = requests.get(
            USERINFO_ENDPOINT,
            headers={"Authorization": f"Bearer {tokens['access_token']}"},
            timeout=10
        )
        logger.info(f"Userinfo response status: {userinfo_response.status_code}")
        if userinfo_response.status_code != 200:
            logger.error(f"Userinfo response body: {userinfo_response.text}")
        userinfo_response.raise_for_status()
        user_info = userinfo_response.json()

        username = user_info.get("preferred_username")

        # Store tokens (in production, encrypt and use a database)
        token_store[username] = {
            "access_token": tokens["access_token"],
            "refresh_token": tokens.get("refresh_token"),
            "expires_in": tokens.get("expires_in", 300)
        }

        # Store in session
        session["username"] = username
        session["email"] = user_info.get("email")

        logger.info(f"Successfully authorized user: {username}")
        logger.info(f"Stored tokens for agent use (has refresh token: {bool(tokens.get('refresh_token'))})")

        return render_template_string(
            SUCCESS_TEMPLATE,
            title="Authorization Successful!",
            message=f"The agent can now act on behalf of {username}.",
            user_info=json.dumps(user_info, indent=2)
        )

    except Exception as e:
        logger.error(f"Error during token exchange: {e}")
        return f"Error: {str(e)}", 500


@app.route("/revoke")
def revoke():
    """Revoke agent access (remove stored tokens)."""
    username = session.get("username")

    if username and username in token_store:
        # In production, also call the revocation endpoint
        del token_store[username]
        session.clear()
        logger.info(f"Revoked tokens for user: {username}")

        return render_template_string(
            SUCCESS_TEMPLATE,
            title="Access Revoked",
            message=f"The agent can no longer act on behalf of {username}."
        )
    else:
        return redirect("/")


@app.route("/test")
def test():
    """Test the stored token by calling the demo API."""
    username = session.get("username")

    if not username or username not in token_store:
        return "No active delegation", 401

    token_info = token_store[username]
    access_token = token_info["access_token"]

    try:
        # Call demo service
        demo_url = os.getenv("DEMO_SERVICE_URL", "http://demo-service:5000")
        response = requests.get(
            f"{demo_url}/api/whoami",
            headers={"Authorization": f"Bearer {access_token}"},
            timeout=10
        )
        response.raise_for_status()
        result = response.json()

        return render_template_string(
            SUCCESS_TEMPLATE,
            title="Token Test Successful!",
            message="The agent's token is valid and working.",
            user_info=json.dumps(result, indent=2)
        )

    except Exception as e:
        logger.error(f"Token test failed: {e}")
        return f"Token test failed: {str(e)}", 500


@app.route("/api/token/<username>")
def get_token(username):
    """API endpoint for the agent to retrieve user tokens."""
    # In production, add authentication for this endpoint!
    if username in token_store:
        return jsonify(token_store[username]), 200
    else:
        return jsonify({"error": "No token found for user"}), 404


@app.route("/health")
def health():
    """Health check endpoint."""
    return jsonify({"status": "healthy"}), 200


if __name__ == "__main__":
    logger.info("Starting consent UI")
    logger.info(f"Keycloak URL: {KEYCLOAK_URL}")
    logger.info(f"Realm: {KEYCLOAK_REALM}")
    logger.info(f"Client ID: {CLIENT_ID}")
    logger.info(f"Redirect URI: {REDIRECT_URI}")

    app.run(host="0.0.0.0", port=8080, debug=False)
