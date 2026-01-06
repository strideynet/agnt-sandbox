#!/usr/bin/env python3
"""
Standard Token Exchange (RFC 8693)

This script demonstrates Keycloak's Standard Token Exchange feature:
1. Obtain a user token (via direct grant for simplicity)
2. Service client exchanges user's token for a new token
3. New token has different audience and potentially different scopes
4. Compare original and exchanged tokens

This demonstrates how a service can exchange a user's token to obtain
a token that represents the service acting on behalf of the user.

Token Exchange Specification: https://datatracker.ietf.org/doc/html/rfc8693
"""

import json
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

# User credentials for obtaining initial token
USER_CLIENT_ID = "user-client"
USER_CLIENT_SECRET = "user-client-secret"
USERNAME = "alice"
PASSWORD = "password"

# Service client that will exchange tokens
SERVICE_CLIENT_ID = "service-client"
SERVICE_CLIENT_SECRET = "service-client-secret"


def decode_token(token: str) -> dict:
    """Decode JWT token without verification (for display purposes)."""
    try:
        decoded = jwt.decode(token, options={"verify_signature": False})
        return decoded
    except Exception as e:
        print(f"Error decoding token: {e}")
        return {}


def obtain_user_token(username: str, password: str) -> Optional[dict]:
    """
    Obtain a user token via direct grant (Resource Owner Password Credentials).

    Note: In production, you'd typically obtain this via authorization code flow.
    We use direct grant here for simplicity in demonstrating token exchange.
    """
    print("=" * 70)
    print("Standard Token Exchange Demo")
    print("=" * 70)
    print()
    print("Step 1: Obtaining user token via direct grant...")

    token_url = f"{KEYCLOAK_URL}/realms/{REALM}/protocol/openid-connect/token"

    data = {
        "grant_type": "password",
        "client_id": USER_CLIENT_ID,
        "client_secret": USER_CLIENT_SECRET,
        "username": username,
        "password": password,
        "scope": "openid profile email",
    }

    log_request("POST", token_url, data=data)
    response = requests.post(token_url, data=data)
    log_response(response)

    if response.status_code != 200:
        print(f"Error obtaining user token. Status: {response.status_code}")
        print(response.text)
        return None

    tokens = response.json()
    print(f"✓ Successfully obtained user token for '{username}'")
    print()

    return tokens


def decode_jwt_header(token: str) -> dict:
    """Decode JWT header without verification."""
    try:
        header = jwt.get_unverified_header(token)
        return header
    except Exception as e:
        print(f"Error decoding header: {e}")
        return {}


def display_token_comparison(original_token: str, exchanged_token: str):
    """Display decoded original and exchanged tokens."""
    print("=" * 70)
    print("Token Comparison")
    print("=" * 70)
    print()

    print("ORIGINAL TOKEN:")
    print(f"Raw: {original_token}")
    print()
    print("Header:")
    print(json.dumps(decode_jwt_header(original_token), indent=2))
    print()
    print("Body:")
    print(json.dumps(decode_token(original_token), indent=2))
    print()
    print("-" * 70)
    print()

    print("EXCHANGED TOKEN:")
    print(f"Raw: {exchanged_token}")
    print()
    print("Header:")
    print(json.dumps(decode_jwt_header(exchanged_token), indent=2))
    print()
    print("Body:")
    print(json.dumps(decode_token(exchanged_token), indent=2))
    print()
    print("-" * 70)
    print()


def exchange_token(subject_token: str, requested_audience: Optional[str] = None) -> Optional[dict]:
    """
    Exchange a token using Standard Token Exchange (RFC 8693).

    Args:
        subject_token: The token to exchange
        requested_audience: Optional target audience for the new token

    Returns:
        Dictionary containing the exchanged token and metadata
    """
    print("Step 2: Exchanging token using Standard Token Exchange (RFC 8693)...")
    print(f"  Service Client: {SERVICE_CLIENT_ID}")
    if requested_audience:
        print(f"  Requested Audience: {requested_audience}")
    print()

    token_url = f"{KEYCLOAK_URL}/realms/{REALM}/protocol/openid-connect/token"

    # Token exchange request according to RFC 8693
    data = {
        "grant_type": "urn:ietf:params:oauth:grant-type:token-exchange",
        "client_id": SERVICE_CLIENT_ID,
        "client_secret": SERVICE_CLIENT_SECRET,
        "subject_token": subject_token,
        "subject_token_type": "urn:ietf:params:oauth:token-type:access_token",
        "requested_token_type": "urn:ietf:params:oauth:token-type:access_token",
    }

    # Add audience if specified
    if requested_audience:
        data["audience"] = requested_audience

    log_request("POST", token_url, data=data)
    response = requests.post(token_url, data=data)
    log_response(response)

    if response.status_code != 200:
        print(f"Error exchanging token. Status: {response.status_code}")
        print("Response:")
        print(response.text)
        print()
        print("Common issues:")
        print("  1. Token exchange not enabled for service-client")
        print("  2. Requested audience not permitted")
        print("  3. Subject token expired or invalid")
        return None

    result = response.json()
    print("✓ Successfully exchanged token")
    print()

    return result


def validate_token(access_token: str):
    """Validate token by calling userinfo endpoint."""
    print("Step 3: Validating exchanged token by calling userinfo endpoint...")

    userinfo_url = f"{KEYCLOAK_URL}/realms/{REALM}/protocol/openid-connect/userinfo"

    headers = {
        "Authorization": f"Bearer {access_token}"
    }

    log_request("GET", userinfo_url, headers=headers)
    response = requests.get(userinfo_url, headers=headers)
    log_response(response)

    if response.status_code != 200:
        print(f"Error calling userinfo. Status: {response.status_code}")
        print(response.text)
        return

    print("✓ Token is valid and can access protected resources")
    print()


def main():
    # Step 1: Obtain user token
    user_tokens = obtain_user_token(USERNAME, PASSWORD)
    if not user_tokens:
        print("Failed to obtain user token")
        return

    user_access_token = user_tokens["access_token"]

    # Step 2: Exchange token (without specifying audience)
    print("Scenario 1: Token Exchange without specific audience")
    print("-" * 70)
    exchanged_tokens = exchange_token(user_access_token)

    if not exchanged_tokens:
        print("Failed to exchange token")
        return

    exchanged_access_token = exchanged_tokens["access_token"]

    # Display comparison
    display_token_comparison(user_access_token, exchanged_access_token)

    # Step 3: Validate exchanged token
    validate_token(exchanged_access_token)

    # Optional: Try with specific audience
    print()
    print("Scenario 2: Token Exchange with specific audience")
    print("-" * 70)
    print("Attempting to exchange with audience=user-client...")
    print()

    exchanged_with_audience = exchange_token(user_access_token, requested_audience=USER_CLIENT_ID)

    if exchanged_with_audience:
        print("✓ Successfully exchanged token with specific audience")
        print()


if __name__ == "__main__":
    main()
