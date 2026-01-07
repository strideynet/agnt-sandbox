#!/usr/bin/env python3
"""
Keycloak Realm Setup for Devoops

This script creates and configures a Keycloak realm for the devoops Mission Control UI.

The realm includes:
- devoops-ui-client: Confidential client for user authentication
- Demo users: alice/password, bob/password
"""

import json
import os
import requests
import sys
import time
from typing import Optional


class KeycloakAdmin:
    def __init__(self, base_url: str, admin_user: str, admin_password: str):
        self.base_url = base_url.rstrip('/')
        self.admin_user = admin_user
        self.admin_password = admin_password
        self.token: Optional[str] = None

    def get_admin_token(self) -> str:
        """Obtain admin token from Keycloak master realm."""
        print("Obtaining admin token...")

        response = requests.post(
            f"{self.base_url}/realms/master/protocol/openid-connect/token",
            data={
                "username": self.admin_user,
                "password": self.admin_password,
                "grant_type": "password",
                "client_id": "admin-cli",
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"}
        )

        if response.status_code != 200:
            print(f"Error: Failed to obtain admin token. Status: {response.status_code}")
            print(response.text)
            sys.exit(1)

        self.token = response.json()["access_token"]
        print("✓ Successfully obtained admin token")
        return self.token

    def headers(self) -> dict:
        """Return headers with authorization token."""
        if not self.token:
            self.get_admin_token()
        return {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json"
        }

    def create_realm(self, realm_name: str) -> bool:
        """Create a new realm with basic configuration."""
        print(f"\nCreating realm: {realm_name}...")

        realm_config = {
            "realm": realm_name,
            "enabled": True,
            "sslRequired": "none",
            "registrationAllowed": False,
            "loginWithEmailAllowed": True,
            "duplicateEmailsAllowed": False,
            "resetPasswordAllowed": True,
            "editUsernameAllowed": False,
            "bruteForceProtected": True,
            "accessTokenLifespan": 300,
            "refreshTokenMaxReuse": 0,
            "ssoSessionIdleTimeout": 1800,
            "ssoSessionMaxLifespan": 36000,
        }

        response = requests.post(
            f"{self.base_url}/admin/realms",
            headers=self.headers(),
            json=realm_config
        )

        if response.status_code == 201:
            print(f"✓ Realm '{realm_name}' created successfully")
            return True
        elif response.status_code == 409:
            print(f"! Realm '{realm_name}' already exists, continuing...")
            return True
        else:
            print(f"Error creating realm. Status: {response.status_code}")
            print(response.text)
            return False

    def create_client(self, realm_name: str, client_config: dict) -> Optional[str]:
        """Create a client and return its internal ID."""
        client_id = client_config["clientId"]
        print(f"\nCreating client: {client_id}...")

        response = requests.post(
            f"{self.base_url}/admin/realms/{realm_name}/clients",
            headers=self.headers(),
            json=client_config
        )

        if response.status_code == 201:
            print(f"✓ Client '{client_id}' created successfully")
            # Get the internal ID
            location = response.headers.get("Location", "")
            internal_id = location.split("/")[-1] if location else None
            return internal_id
        elif response.status_code == 409:
            print(f"! Client '{client_id}' already exists")
            return self.get_client_id(realm_name, client_id)
        else:
            print(f"Error creating client. Status: {response.status_code}")
            print(response.text)
            return None

    def get_client_id(self, realm_name: str, client_id: str) -> Optional[str]:
        """Get the internal ID of a client by its clientId."""
        response = requests.get(
            f"{self.base_url}/admin/realms/{realm_name}/clients",
            headers=self.headers(),
            params={"clientId": client_id}
        )

        if response.status_code == 200:
            clients = response.json()
            if clients:
                return clients[0]["id"]
        return None

    def create_user(self, realm_name: str, username: str, password: str,
                   email: str, first_name: str, last_name: str) -> bool:
        """Create a user with credentials."""
        print(f"\nCreating user: {username}...")

        user_config = {
            "username": username,
            "email": email,
            "firstName": first_name,
            "lastName": last_name,
            "enabled": True,
            "emailVerified": True,
            "credentials": [{
                "type": "password",
                "value": password,
                "temporary": False
            }]
        }

        response = requests.post(
            f"{self.base_url}/admin/realms/{realm_name}/users",
            headers=self.headers(),
            json=user_config
        )

        if response.status_code == 201:
            print(f"✓ User '{username}' created (password: {password})")
            return True
        elif response.status_code == 409:
            print(f"! User '{username}' already exists")
            return True
        else:
            print(f"Error creating user. Status: {response.status_code}")
            print(response.text)
            return False


def wait_for_keycloak(keycloak_url: str, max_attempts: int = 30) -> bool:
    """Wait for Keycloak to be ready."""
    print("Waiting for Keycloak to be ready...")

    for i in range(1, max_attempts + 1):
        try:
            # Try to access the master realm - if this works, Keycloak is ready
            response = requests.get(f"{keycloak_url}/realms/master", timeout=5)
            if response.status_code == 200:
                print("✓ Keycloak is ready!")
                return True
        except requests.exceptions.RequestException:
            pass

        if i == max_attempts:
            print("Error: Keycloak did not become ready in time")
            return False

        print(f"Waiting... ({i}/{max_attempts})")
        time.sleep(2)

    return False


def main():
    # Configuration from environment or defaults
    KEYCLOAK_URL = os.environ.get("KEYCLOAK_URL", "http://localhost:30080")
    ADMIN_USER = os.environ.get("KEYCLOAK_ADMIN", "admin")
    ADMIN_PASSWORD = os.environ.get("KEYCLOAK_ADMIN_PASSWORD", "admin")
    REALM_NAME = "devoops"

    print("=" * 60)
    print("Keycloak Devoops Realm Setup")
    print("=" * 60)
    print(f"Keycloak URL: {KEYCLOAK_URL}")
    print(f"Realm: {REALM_NAME}")
    print()

    # Wait for Keycloak
    if not wait_for_keycloak(KEYCLOAK_URL):
        sys.exit(1)

    # Initialize admin client
    admin = KeycloakAdmin(KEYCLOAK_URL, ADMIN_USER, ADMIN_PASSWORD)
    admin.get_admin_token()

    # Create realm
    if not admin.create_realm(REALM_NAME):
        print("Failed to create realm")
        sys.exit(1)

    # Create devoops-ui-client (for OAuth2 authorization code flow)
    ui_client_config = {
        "clientId": "devoops-ui-client",
        "name": "Devoops Mission Control UI",
        "description": "Web UI for DevOps agent mission control",
        "enabled": True,
        "clientAuthenticatorType": "client-secret",
        "secret": "devoops-ui-secret-change-in-production",
        "redirectUris": ["http://localhost:30900/*"],
        "webOrigins": ["+"],
        "protocol": "openid-connect",
        "publicClient": False,
        "standardFlowEnabled": True,
        "directAccessGrantsEnabled": False,
        "serviceAccountsEnabled": False,
        "authorizationServicesEnabled": False,
        "attributes": {
            "oauth2.device.authorization.grant.enabled": "false",
            "oidc.ciba.grant.enabled": "false",
        },
        "defaultClientScopes": ["web-origins", "acr", "profile", "roles", "email"],
        "optionalClientScopes": ["address", "phone", "offline_access", "microprofile-jwt"]
    }

    ui_client_id = admin.create_client(REALM_NAME, ui_client_config)
    if not ui_client_id:
        print("Failed to create devoops-ui-client")
        sys.exit(1)

    # Create demo users
    demo_users = [
        ("alice", "password", "alice@example.com", "Alice", "DevOps"),
        ("bob", "password", "bob@example.com", "Bob", "Engineer"),
    ]

    for username, password, email, first_name, last_name in demo_users:
        admin.create_user(REALM_NAME, username, password, email, first_name, last_name)

    # Display summary
    print()
    print("=" * 60)
    print("Configuration Summary")
    print("=" * 60)
    print(f"Keycloak Admin Console: {KEYCLOAK_URL}/admin")
    print(f"  Username: {ADMIN_USER}")
    print(f"  Password: {ADMIN_PASSWORD}")
    print()
    print(f"Realm: {REALM_NAME}")
    print()
    print("Client:")
    print(f"  devoops-ui-client:")
    print(f"    Client ID: devoops-ui-client")
    print(f"    Client Secret: devoops-ui-secret-change-in-production")
    print(f"    Purpose: User authentication for Mission Control UI")
    print()
    print("Demo Users:")
    print("  alice / password")
    print("  bob / password")
    print()
    print("Endpoints:")
    print(f"  Token: {KEYCLOAK_URL}/realms/{REALM_NAME}/protocol/openid-connect/token")
    print(f"  Authorize: {KEYCLOAK_URL}/realms/{REALM_NAME}/protocol/openid-connect/auth")
    print(f"  Userinfo: {KEYCLOAK_URL}/realms/{REALM_NAME}/protocol/openid-connect/userinfo")
    print()
    print("Mission Control UI:")
    print(f"  URL: http://localhost:30900")
    print(f"  Login with: alice/password or bob/password")
    print()
    print("=" * 60)
    print("Setup Complete!")
    print("=" * 60)


if __name__ == "__main__":
    main()
