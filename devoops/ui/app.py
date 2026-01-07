"""
Mission Control UI - Devoops Agent

This web application allows users to submit missions to the devoops agent
and monitor their execution in real-time.

Requires OAuth2 authentication via Keycloak.
"""

import os
import logging
import secrets
from functools import wraps
from urllib.parse import urlencode
from flask import Flask, render_template_string, request, redirect, jsonify, session
import requests

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
REDIRECT_URI = os.getenv("REDIRECT_URI", "http://localhost:30900/callback")

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
            # Redirect to login page instead of directly to Keycloak
            return redirect("/login-page")
        return f(*args, **kwargs)
    return decorated_function

# HTML Templates
LOGIN_PAGE_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <title>Login - Devoops Mission Control</title>
    <style>
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
            max-width: 600px;
            margin: 100px auto;
            padding: 20px;
            background: #f5f5f5;
            text-align: center;
        }
        .container {
            background: white;
            padding: 60px 40px;
            border-radius: 8px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        }
        .robot { font-size: 80px; margin-bottom: 20px; }
        h1 {
            color: #333;
            margin-bottom: 10px;
        }
        .subtitle {
            color: #666;
            margin-bottom: 40px;
            font-size: 18px;
        }
        .info-box {
            background: #e7f3ff;
            border-left: 4px solid #007bff;
            padding: 20px;
            margin: 30px 0;
            text-align: left;
        }
        .button {
            display: inline-block;
            padding: 16px 32px;
            background: #007bff;
            color: white;
            text-decoration: none;
            border-radius: 4px;
            border: none;
            cursor: pointer;
            font-size: 18px;
            font-weight: 500;
        }
        .button:hover { background: #0056b3; }
        .note {
            margin-top: 30px;
            color: #999;
            font-size: 14px;
        }
    </style>
</head>
<body>
    <div class="container">
        <div class="robot">🤖</div>
        <h1>Devoops Mission Control</h1>
        <p class="subtitle">DevOps Agent for Kubernetes</p>

        <div class="info-box">
            <strong>Authentication Required</strong><br><br>
            You need to log in to access the Mission Control interface and submit missions to the DevOps agent.
        </div>

        <a href="/login" class="button">Log In with Keycloak</a>

        <p class="note">
            Demo users: alice / password, bob / password
        </p>
    </div>
</body>
</html>
"""

HOME_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <title>Devoops - Mission Control</title>
    <style>
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
            max-width: 1200px;
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
        h1 {
            color: #333;
            margin-bottom: 10px;
            display: flex;
            align-items: center;
            gap: 10px;
        }
        .robot { font-size: 40px; }
        .subtitle { color: #666; margin-bottom: 30px; }
        .mission-form {
            background: #f8f9fa;
            padding: 20px;
            border-radius: 4px;
            margin: 20px 0;
        }
        .mission-form textarea {
            width: 100%;
            padding: 12px;
            border: 1px solid #ddd;
            border-radius: 4px;
            font-family: inherit;
            font-size: 14px;
            resize: vertical;
            min-height: 100px;
            box-sizing: border-box;
        }
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
            margin-top: 10px;
        }
        .button:hover { background: #0056b3; }
        .button:disabled {
            background: #ccc;
            cursor: not-allowed;
        }
        .missions-list {
            margin-top: 40px;
        }
        .mission-card {
            background: #f8f9fa;
            border-left: 4px solid #007bff;
            padding: 15px;
            margin: 15px 0;
            border-radius: 4px;
            cursor: pointer;
            transition: box-shadow 0.2s;
        }
        .mission-card:hover {
            box-shadow: 0 2px 8px rgba(0,0,0,0.1);
        }
        .mission-card.completed {
            border-left-color: #28a745;
        }
        .mission-card.failed {
            border-left-color: #dc3545;
        }
        .mission-card.running {
            border-left-color: #ffc107;
        }
        .mission-header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 10px;
        }
        .mission-id {
            font-weight: bold;
            color: #333;
        }
        .status-badge {
            padding: 4px 12px;
            border-radius: 12px;
            font-size: 12px;
            font-weight: 600;
            text-transform: uppercase;
        }
        .status-badge.pending {
            background: #e7f3ff;
            color: #007bff;
        }
        .status-badge.running {
            background: #fff3cd;
            color: #856404;
        }
        .status-badge.completed {
            background: #d4edda;
            color: #155724;
        }
        .status-badge.failed {
            background: #f8d7da;
            color: #721c24;
        }
        .mission-prompt {
            color: #666;
            font-size: 14px;
            margin: 10px 0;
            font-style: italic;
        }
        .mission-time {
            color: #999;
            font-size: 12px;
        }
        .info-box {
            background: #e7f3ff;
            border-left: 4px solid #007bff;
            padding: 15px;
            margin: 20px 0;
        }
        .examples {
            background: #f8f9fa;
            padding: 15px;
            border-radius: 4px;
            margin: 20px 0;
        }
        .examples h3 {
            margin-top: 0;
            color: #333;
        }
        .examples ul {
            margin: 10px 0;
            padding-left: 20px;
        }
        .examples li {
            margin: 8px 0;
            color: #666;
        }
        .error-box {
            background: #f8d7da;
            border-left: 4px solid #dc3545;
            padding: 15px;
            margin: 20px 0;
            color: #721c24;
        }
    </style>
</head>
<body>
    <div class="container">
        <div style="display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 20px;">
            <div>
                <h1>
                    <span class="robot">🤖</span>
                    Devoops Mission Control
                </h1>
                <p class="subtitle">Submit DevOps missions to your Kubernetes agent</p>
            </div>
            <div style="text-align: right;">
                <p style="margin: 0; color: #666;">Logged in as: <strong>{{ user.username }}</strong></p>
                <p style="margin: 5px 0 0 0; color: #999; font-size: 14px;">{{ user.email }}</p>
                <a href="/logout" style="color: #007bff; text-decoration: none; font-size: 14px;">Logout</a>
            </div>
        </div>

        <div class="info-box">
            <strong>How it works:</strong><br>
            Submit a natural language mission describing what you want the agent to do in your
            Kubernetes cluster. The agent will use Claude to reason about the task and execute
            the necessary operations.
        </div>

        <div class="mission-form">
            <h2>Submit New Mission</h2>
            <form id="missionForm" onsubmit="return submitMission(event)">
                <textarea
                    id="missionPrompt"
                    name="prompt"
                    placeholder="e.g., Check if there are any crashlooping pods in the default namespace and investigate why"
                    required
                ></textarea>
                <button type="submit" class="button" id="submitBtn">
                    🚀 Launch Mission
                </button>
            </form>
        </div>

        <div class="examples">
            <h3>Example Missions:</h3>
            <ul>
                <li>"List all pods in the default namespace"</li>
                <li>"Scale the nginx deployment to 3 replicas"</li>
                <li>"Find all pods using more than 500Mi of memory"</li>
                <li>"Check if there are any crashlooping pods and investigate why"</li>
                <li>"Deploy a simple nginx web server with a Service and test it"</li>
            </ul>
        </div>

        <div class="missions-list">
            <h2>Mission History</h2>
            <div id="missionsList">
                <p style="color: #999;">Loading missions...</p>
            </div>
        </div>
    </div>

    <script>
        async function submitMission(event) {
            event.preventDefault();

            const prompt = document.getElementById('missionPrompt').value;
            const submitBtn = document.getElementById('submitBtn');

            submitBtn.disabled = true;
            submitBtn.textContent = '🚀 Launching...';

            try {
                const response = await fetch('/api/missions', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                    },
                    body: JSON.stringify({ prompt }),
                });

                if (response.ok) {
                    const mission = await response.json();
                    document.getElementById('missionPrompt').value = '';
                    window.location.href = `/missions/${mission.id}`;
                } else {
                    const error = await response.json();
                    alert('Failed to submit mission: ' + (error.error || 'Unknown error'));
                }
            } catch (error) {
                alert('Failed to submit mission: ' + error.message);
            } finally {
                submitBtn.disabled = false;
                submitBtn.textContent = '🚀 Launch Mission';
            }
        }

        async function loadMissions() {
            try {
                const response = await fetch('/api/missions');
                const missions = await response.json();

                const listEl = document.getElementById('missionsList');

                if (missions.length === 0) {
                    listEl.innerHTML = '<p style="color: #999;">No missions yet. Submit your first mission above!</p>';
                    return;
                }

                // Sort by created_at descending
                missions.sort((a, b) => new Date(b.created_at) - new Date(a.created_at));

                listEl.innerHTML = missions.map(mission => `
                    <div class="mission-card ${mission.status}" onclick="window.location.href='/missions/${mission.id}'">
                        <div class="mission-header">
                            <span class="mission-id">${mission.id}</span>
                            <span class="status-badge ${mission.status}">${mission.status}</span>
                        </div>
                        <div class="mission-prompt">"${mission.prompt}"</div>
                        <div class="mission-time">Created: ${new Date(mission.created_at).toLocaleString()}</div>
                    </div>
                `).join('');
            } catch (error) {
                console.error('Failed to load missions:', error);
                document.getElementById('missionsList').innerHTML =
                    '<p style="color: #dc3545;">Failed to load missions. Is the agent running?</p>';
            }
        }

        // Load missions on page load
        loadMissions();

        // Refresh missions every 500ms for responsive updates
        setInterval(loadMissions, 500);
    </script>
</body>
</html>
"""

MISSION_DETAIL_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <title>Mission {{ mission.id }} - Devoops</title>
    <style>
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
            max-width: 1200px;
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
        .header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 30px;
        }
        h1 {
            color: #333;
            margin: 0;
        }
        .status-badge {
            padding: 8px 16px;
            border-radius: 16px;
            font-size: 14px;
            font-weight: 600;
            text-transform: uppercase;
        }
        .status-badge.pending {
            background: #e7f3ff;
            color: #007bff;
        }
        .status-badge.running {
            background: #fff3cd;
            color: #856404;
        }
        .status-badge.completed {
            background: #d4edda;
            color: #155724;
        }
        .status-badge.failed {
            background: #f8d7da;
            color: #721c24;
        }
        .mission-info {
            background: #f8f9fa;
            padding: 20px;
            border-radius: 4px;
            margin: 20px 0;
        }
        .mission-info h3 {
            margin-top: 0;
            color: #333;
        }
        .prompt {
            font-style: italic;
            color: #666;
            padding: 10px;
            background: white;
            border-left: 4px solid #007bff;
        }
        .logs {
            background: #1e1e1e;
            color: #d4d4d4;
            padding: 20px;
            border-radius: 4px;
            margin: 20px 0;
            font-family: 'Monaco', 'Courier New', monospace;
            font-size: 13px;
            max-height: 500px;
            overflow-y: auto;
        }
        .log-entry {
            margin: 5px 0;
            line-height: 1.5;
        }
        .result {
            background: #d4edda;
            border-left: 4px solid #28a745;
            padding: 20px;
            margin: 20px 0;
            border-radius: 4px;
        }
        .result h3 {
            margin-top: 0;
            color: #155724;
        }
        .result-content {
            white-space: pre-wrap;
            color: #155724;
        }
        .error {
            background: #f8d7da;
            border-left: 4px solid #dc3545;
            padding: 20px;
            margin: 20px 0;
            border-radius: 4px;
        }
        .error h3 {
            margin-top: 0;
            color: #721c24;
        }
        .error-content {
            white-space: pre-wrap;
            color: #721c24;
        }
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
        .timestamp {
            color: #999;
            font-size: 12px;
        }
        .spinner {
            display: inline-block;
            width: 14px;
            height: 14px;
            border: 2px solid #856404;
            border-radius: 50%;
            border-top-color: transparent;
            animation: spin 1s linear infinite;
            margin-left: 8px;
        }
        @keyframes spin {
            to { transform: rotate(360deg); }
        }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>{{ mission.id }}</h1>
            <span class="status-badge {{ mission.status }}">
                {{ mission.status }}
                {% if mission.status == 'running' %}
                <span class="spinner"></span>
                {% endif %}
            </span>
        </div>

        <div class="mission-info">
            <h3>Mission Prompt:</h3>
            <div class="prompt">{{ mission.prompt }}</div>

            <p class="timestamp">
                <strong>Created:</strong> {{ mission.created_at }}<br>
                {% if mission.started_at %}
                <strong>Started:</strong> {{ mission.started_at }}<br>
                {% endif %}
                {% if mission.completed_at %}
                <strong>Completed:</strong> {{ mission.completed_at }}
                {% endif %}
            </p>
        </div>

        {% if mission.result %}
        <div class="result">
            <h3>✓ Mission Result:</h3>
            <div class="result-content">{{ mission.result }}</div>
        </div>
        {% endif %}

        {% if mission.error %}
        <div class="error">
            <h3>✗ Error:</h3>
            <div class="error-content">{{ mission.error }}</div>
        </div>
        {% endif %}

        <h3>Execution Logs:</h3>
        <div class="logs" id="logs">
            {% if mission.logs %}
                {% for log in mission.logs %}
                <div class="log-entry">{{ log }}</div>
                {% endfor %}
            {% else %}
                <div class="log-entry" style="color: #999;">No logs yet...</div>
            {% endif %}
        </div>

        <p>
            <a href="/" class="button">← Back to Mission Control</a>
        </p>
    </div>

    <script>
        const missionId = "{{ mission.id }}";
        let currentStatus = "{{ mission.status }}";
        let pollInterval = null;

        async function refreshMission() {
            try {
                const response = await fetch(`/api/missions/${missionId}`);
                const mission = await response.json();

                // Update status badge
                const statusBadge = document.querySelector('.status-badge');
                if (mission.status !== currentStatus) {
                    statusBadge.className = `status-badge ${mission.status}`;

                    // Update spinner
                    if (mission.status === 'running') {
                        statusBadge.innerHTML = `${mission.status} <span class="spinner"></span>`;
                    } else {
                        statusBadge.textContent = mission.status;
                    }

                    currentStatus = mission.status;
                }

                // Update timestamps
                const timestampEl = document.querySelector('.timestamp');
                let timestampHTML = `<strong>Created:</strong> ${mission.created_at}<br>`;
                if (mission.started_at) {
                    timestampHTML += `<strong>Started:</strong> ${mission.started_at}<br>`;
                }
                if (mission.completed_at) {
                    timestampHTML += `<strong>Completed:</strong> ${mission.completed_at}`;
                }
                timestampEl.innerHTML = timestampHTML;

                // Update logs
                const logsEl = document.getElementById('logs');
                if (mission.logs && mission.logs.length > 0) {
                    logsEl.innerHTML = mission.logs.map(log =>
                        `<div class="log-entry">${log}</div>`
                    ).join('');
                    // Auto-scroll to bottom
                    logsEl.scrollTop = logsEl.scrollHeight;
                } else {
                    logsEl.innerHTML = '<div class="log-entry" style="color: #999;">No logs yet...</div>';
                }

                // Update or add result section
                let resultSection = document.querySelector('.result');
                if (mission.result) {
                    if (!resultSection) {
                        resultSection = document.createElement('div');
                        resultSection.className = 'result';
                        document.querySelector('.logs').insertAdjacentElement('beforebegin', resultSection);
                    }
                    resultSection.innerHTML = `
                        <h3>✓ Mission Result:</h3>
                        <div class="result-content">${mission.result}</div>
                    `;
                }

                // Update or add error section
                let errorSection = document.querySelector('.error');
                if (mission.error) {
                    if (!errorSection) {
                        errorSection = document.createElement('div');
                        errorSection.className = 'error';
                        document.querySelector('.logs').insertAdjacentElement('beforebegin', errorSection);
                    }
                    errorSection.innerHTML = `
                        <h3>✗ Error:</h3>
                        <div class="error-content">${mission.error}</div>
                    `;
                }

                // Stop polling if mission is completed or failed
                if (mission.status === 'completed' || mission.status === 'failed') {
                    if (pollInterval) {
                        clearInterval(pollInterval);
                        pollInterval = null;
                        console.log('Mission finished, stopped polling');
                    }
                }
            } catch (error) {
                console.error('Failed to refresh mission:', error);
            }
        }

        // Start polling if mission is pending or running
        if (currentStatus === 'pending' || currentStatus === 'running') {
            console.log('Starting polling for mission updates');
            // Initial update
            refreshMission();
            // Poll every 500ms for responsive updates
            pollInterval = setInterval(refreshMission, 500);
        }
    </script>
</body>
</html>
"""


@app.route("/")
@login_required
def home():
    """Home page with mission submission form."""
    user = {
        "username": session.get("username"),
        "email": session.get("email")
    }
    return render_template_string(HOME_TEMPLATE, user=user)


@app.route("/missions/<mission_id>")
@login_required
def mission_detail(mission_id):
    """Mission detail page."""
    try:
        response = requests.get(f"{AGENT_URL}/api/missions/{mission_id}", timeout=10)
        response.raise_for_status()
        mission = response.json()

        return render_template_string(MISSION_DETAIL_TEMPLATE, mission=mission)
    except Exception as e:
        logger.error(f"Failed to fetch mission {mission_id}: {e}")
        return f"Error loading mission: {str(e)}", 500


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


@app.route("/login-page")
def login_page():
    """Show login page with information about authentication."""
    return render_template_string(LOGIN_PAGE_TEMPLATE)


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
    logger.info(f"Redirecting to Keycloak for authentication")

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

        logger.info("✓ Token exchange successful")
        logger.info(f"Access token (first 50 chars): {tokens['access_token'][:50]}...")

        # Decode JWT to inspect claims (just for debugging)
        import base64
        import json as json_module
        try:
            # Split JWT and decode payload (2nd part)
            parts = tokens['access_token'].split('.')
            if len(parts) == 3:
                # Add padding if needed
                payload = parts[1]
                payload += '=' * (4 - len(payload) % 4)
                decoded = base64.urlsafe_b64decode(payload)
                claims = json_module.loads(decoded)
                logger.info(f"Token issuer (iss): {claims.get('iss')}")
                logger.info(f"Token audience (aud): {claims.get('aud')}")
                logger.info(f"Token subject (sub): {claims.get('sub')}")
        except Exception as decode_err:
            logger.warning(f"Could not decode token for inspection: {decode_err}")

        # Get user info
        logger.info("Fetching user information...")
        logger.info(f"USERINFO_ENDPOINT: {USERINFO_ENDPOINT}")
        userinfo_response = requests.get(
            USERINFO_ENDPOINT,
            headers={"Authorization": f"Bearer {tokens['access_token']}"},
            timeout=10
        )
        logger.info(f"Userinfo response status: {userinfo_response.status_code}")
        userinfo_response.raise_for_status()
        user_info = userinfo_response.json()

        username = user_info.get("preferred_username")
        email = user_info.get("email")

        # Store in session
        session["username"] = username
        session["email"] = email
        session["access_token"] = tokens["access_token"]

        logger.info(f"✓ User logged in: {username}")

        return redirect("/")

    except Exception as e:
        logger.error(f"Error during OAuth2 flow: {e}")
        return f"Authentication error: {str(e)}", 500


@app.route("/logout")
def logout():
    """Clear session and redirect to Keycloak logout."""
    username = session.get("username")
    session.clear()

    logger.info(f"User logged out: {username}")

    # Redirect to Keycloak logout
    redirect_url = request.url_root
    logout_url = f"{LOGOUT_ENDPOINT}?redirect_uri={redirect_url}"

    return redirect(logout_url)


@app.route("/health")
def health():
    """Health check endpoint."""
    return jsonify({"status": "healthy"}), 200


if __name__ == "__main__":
    logger.info("Starting Mission Control UI")
    logger.info(f"Agent URL: {AGENT_URL}")
    logger.info(f"Keycloak URL: {KEYCLOAK_URL}")
    logger.info(f"Keycloak Realm: {KEYCLOAK_REALM}")
    logger.info(f"Client ID: {CLIENT_ID}")
    logger.info(f"Redirect URI: {REDIRECT_URI}")

    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port, debug=False)
