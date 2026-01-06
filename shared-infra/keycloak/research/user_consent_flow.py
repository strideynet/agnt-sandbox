#!/usr/bin/env python3
"""
OAuth2 Authorization Code Flow with User Consent

This script demonstrates the standard OAuth2 authorization code flow:
1. User authenticates in the browser
2. User grants consent to the application
3. Application receives authorization code
4. Application exchanges code for tokens
5. Application can use access token and refresh it when expired

This simulates a user giving consent to a client application to act on their behalf.
"""

import base64
import hashlib
import json
import secrets
import webbrowser
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlencode, urlparse, parse_qs
from typing import Optional

import jwt
import requests


def log_request(method: str, url: str, data=None, headers=None):
    """Log HTTP request details for developers."""
    print(f"\n{'=' * 70}")
    print(f"→ REQUEST: {method} {url}")
    if headers:
        print(f"  Headers:")
        for k, v in headers.items():
            print(f"    {k}: {v}")
    if data:
        print(f"  Data:")
        for k, v in data.items():
            print(f"    {k}: {v}")
    print(f"{'=' * 70}")


def log_response(response: requests.Response):
    """Log HTTP response details for developers."""
    print(f"\n{'=' * 70}")
    print(f"← RESPONSE: {response.status_code} {response.reason}")
    print(f"  Headers:")
    for k, v in response.headers.items():
        print(f"    {k}: {v}")
    try:
        if response.headers.get('content-type', '').startswith('application/json'):
            json_resp = response.json()
            print(f"  Body:")
            print(json.dumps(json_resp, indent=4))
        else:
            print(f"  Body: {response.text}")
    except Exception:
        print(f"  Body: {response.text}")
    print(f"{'=' * 70}\n")


# Configuration
KEYCLOAK_URL = "http://localhost:30080"
REALM = "research"
CLIENT_ID = "user-client"
CLIENT_SECRET = "user-client-secret"
REDIRECT_URI = "http://localhost:8080/callback"
CALLBACK_PORT = 8080

# Store authorization code from callback
authorization_code: Optional[str] = None


class CallbackHandler(BaseHTTPRequestHandler):
    """HTTP handler to receive OAuth2 callback."""

    def do_GET(self):
        global authorization_code

        # Parse query parameters
        parsed = urlparse(self.path)
        params = parse_qs(parsed.query)

        if "code" in params:
            authorization_code = params["code"][0]
            self.send_response(200)
            self.send_header("Content-type", "text/html")
            self.end_headers()
            self.wfile.write(b"""
                <html>
                <body>
                    <h1>Authorization Successful!</h1>
                    <p>You can close this window and return to the terminal.</p>
                </body>
                </html>
            """)
        elif "error" in params:
            error = params["error"][0]
            error_desc = params.get("error_description", ["Unknown error"])[0]
            self.send_response(400)
            self.send_header("Content-type", "text/html")
            self.end_headers()
            self.wfile.write(f"""
                <html>
                <body>
                    <h1>Authorization Failed</h1>
                    <p>Error: {error}</p>
                    <p>Description: {error_desc}</p>
                </body>
                </html>
            """.encode())
        else:
            self.send_response(400)
            self.send_header("Content-type", "text/plain")
            self.end_headers()
            self.wfile.write(b"Missing authorization code")

    def log_message(self, format, *args):
        # Suppress logging
        pass


def generate_pkce_pair():
    """Generate PKCE code verifier and challenge (optional but recommended)."""
    code_verifier = base64.urlsafe_b64encode(secrets.token_bytes(32)).decode('utf-8').rstrip('=')
    code_challenge = base64.urlsafe_b64encode(
        hashlib.sha256(code_verifier.encode('utf-8')).digest()
    ).decode('utf-8').rstrip('=')
    return code_verifier, code_challenge


def start_authorization_flow():
    """Start OAuth2 authorization code flow by opening browser."""
    print("=" * 60)
    print("OAuth2 Authorization Code Flow - User Consent Demo")
    print("=" * 60)
    print()

    # Generate PKCE parameters (optional but recommended)
    code_verifier, code_challenge = generate_pkce_pair()
    state = secrets.token_urlsafe(16)

    # Build authorization URL
    auth_params = {
        "client_id": CLIENT_ID,
        "redirect_uri": REDIRECT_URI,
        "response_type": "code",
        "scope": "openid profile email",
        "state": state,
        "code_challenge": code_challenge,
        "code_challenge_method": "S256",
    }

    auth_url = f"{KEYCLOAK_URL}/realms/{REALM}/protocol/openid-connect/auth?{urlencode(auth_params)}"

    print("Step 1: Opening browser for user authentication...")
    print(f"Authorization URL: {auth_url}")
    print()
    print("Please log in using one of these demo users:")
    print("  - alice / password")
    print("  - bob / password")
    print()

    # Open browser
    webbrowser.open(auth_url)

    # Start local HTTP server to receive callback
    print(f"Step 2: Starting local server on port {CALLBACK_PORT} to receive callback...")
    server = HTTPServer(("localhost", CALLBACK_PORT), CallbackHandler)

    # Wait for callback
    print("Waiting for authorization callback...")
    while authorization_code is None:
        server.handle_request()

    print("✓ Received authorization code")
    print()

    return authorization_code, code_verifier


def exchange_code_for_tokens(auth_code: str, code_verifier: str):
    """Exchange authorization code for access and refresh tokens."""
    print("Step 3: Exchanging authorization code for tokens...")

    token_url = f"{KEYCLOAK_URL}/realms/{REALM}/protocol/openid-connect/token"

    data = {
        "grant_type": "authorization_code",
        "code": auth_code,
        "redirect_uri": REDIRECT_URI,
        "client_id": CLIENT_ID,
        "client_secret": CLIENT_SECRET,
        "code_verifier": code_verifier,
    }

    log_request("POST", token_url, data=data)
    response = requests.post(token_url, data=data)
    log_response(response)

    if response.status_code != 200:
        print(f"Error exchanging code for tokens. Status: {response.status_code}")
        print(response.text)
        return None

    tokens = response.json()
    print("✓ Successfully obtained tokens")
    print()

    return tokens


def decode_token(token: str):
    """Decode JWT token without verification (for display purposes)."""
    try:
        # Decode without verification (just for display)
        decoded = jwt.decode(token, options={"verify_signature": False})
        return decoded
    except Exception as e:
        print(f"Error decoding token: {e}")
        return None


def decode_jwt_header(token: str) -> dict:
    """Decode JWT header without verification."""
    try:
        header = jwt.get_unverified_header(token)
        return header
    except Exception as e:
        print(f"Error decoding header: {e}")
        return {}


def display_token_info(tokens: dict):
    """Display decoded JWT tokens."""
    print("=" * 70)
    print("Decoded Tokens")
    print("=" * 70)
    print()

    # Access Token
    if "access_token" in tokens:
        access_token = tokens["access_token"]
        print("ACCESS TOKEN:")
        print(f"Raw: {access_token}")
        print()
        print("Header:")
        print(json.dumps(decode_jwt_header(access_token), indent=2))
        print()
        print("Body:")
        decoded = decode_token(access_token)
        if decoded:
            print(json.dumps(decoded, indent=2))
        print()
        print("-" * 70)
        print()

    # Refresh Token
    if "refresh_token" in tokens:
        refresh_token = tokens["refresh_token"]
        print("REFRESH TOKEN:")
        print(f"Raw: {refresh_token}")
        print()
        print("Header:")
        print(json.dumps(decode_jwt_header(refresh_token), indent=2))
        print()
        print("Body:")
        decoded = decode_token(refresh_token)
        if decoded:
            print(json.dumps(decoded, indent=2))
        print()
        print("-" * 70)
        print()

    # ID Token
    if "id_token" in tokens:
        id_token = tokens["id_token"]
        print("ID TOKEN:")
        print(f"Raw: {id_token}")
        print()
        print("Header:")
        print(json.dumps(decode_jwt_header(id_token), indent=2))
        print()
        print("Body:")
        decoded = decode_token(id_token)
        if decoded:
            print(json.dumps(decoded, indent=2))
        print()
        print("-" * 70)
        print()


def refresh_access_token(refresh_token: str):
    """Use refresh token to obtain a new access token."""
    print("Step 4: Refreshing access token using refresh token...")

    token_url = f"{KEYCLOAK_URL}/realms/{REALM}/protocol/openid-connect/token"

    data = {
        "grant_type": "refresh_token",
        "refresh_token": refresh_token,
        "client_id": CLIENT_ID,
        "client_secret": CLIENT_SECRET,
    }

    log_request("POST", token_url, data=data)
    response = requests.post(token_url, data=data)
    log_response(response)

    if response.status_code != 200:
        print(f"Error refreshing token. Status: {response.status_code}")
        print(response.text)
        return None

    tokens = response.json()
    print("✓ Successfully refreshed access token")
    print()

    return tokens


def get_userinfo(access_token: str):
    """Call userinfo endpoint to get user information."""
    print("Step 5: Calling userinfo endpoint with access token...")

    userinfo_url = f"{KEYCLOAK_URL}/realms/{REALM}/protocol/openid-connect/userinfo"

    headers = {
        "Authorization": f"Bearer {access_token}"
    }

    log_request("GET", userinfo_url, headers=headers)
    response = requests.get(userinfo_url, headers=headers)
    log_response(response)

    if response.status_code != 200:
        print(f"Error getting userinfo. Status: {response.status_code}")
        print(response.text)
        return None

    userinfo = response.json()
    print("✓ Successfully retrieved user information")
    print()

    return userinfo


def main():
    # Step 1 & 2: Start authorization flow and get authorization code
    auth_code, code_verifier = start_authorization_flow()

    # Step 3: Exchange code for tokens
    tokens = exchange_code_for_tokens(auth_code, code_verifier)
    if not tokens:
        print("Failed to obtain tokens")
        return

    # Display token information
    display_token_info(tokens)

    # Step 4: Refresh the access token
    if "refresh_token" in tokens:
        refreshed_tokens = refresh_access_token(tokens["refresh_token"])

    # Step 5: Use access token to call userinfo endpoint
    if "access_token" in tokens:
        get_userinfo(tokens["access_token"])


if __name__ == "__main__":
    main()
