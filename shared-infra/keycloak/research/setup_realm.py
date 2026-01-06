#!/usr/bin/env python3
"""
Keycloak Realm Setup for Research Experiments

This script creates and configures a Keycloak realm for demonstrating:
1. OAuth2 Authorization Code Flow with user consent
2. Standard Token Exchange (RFC 8693)

The realm includes:
- user-client: Confidential client for user authentication (source of tokens)
- service-client: Confidential client that can exchange tokens
- Demo users: alice/password, bob/password
"""

import json
import requests
import sys
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
            "registrationAllowed": True,
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
            # Get existing client ID
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

    def add_audience_mapper(self, realm_name: str, client_internal_id: str,
                           audience_client_id: str) -> bool:
        """Add an audience protocol mapper to include another client in the audience."""
        print(f"\nAdding audience mapper for {audience_client_id}...")

        mapper_config = {
            "name": f"audience-{audience_client_id}",
            "protocol": "openid-connect",
            "protocolMapper": "oidc-audience-mapper",
            "config": {
                "included.client.audience": audience_client_id,
                "access.token.claim": "true",
                "id.token.claim": "false"
            }
        }

        response = requests.post(
            f"{self.base_url}/admin/realms/{realm_name}/clients/{client_internal_id}/protocol-mappers/models",
            headers=self.headers(),
            json=mapper_config
        )

        if response.status_code == 201:
            print(f"✓ Audience mapper added for {audience_client_id}")
            return True
        elif response.status_code == 409:
            print(f"! Audience mapper already exists for {audience_client_id}")
            return True
        else:
            print(f"Warning: Could not add audience mapper. Status: {response.status_code}")
            print(response.text)
            return False

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


def main():
    # Configuration
    KEYCLOAK_URL = "http://localhost:30080"
    ADMIN_USER = "admin"
    ADMIN_PASSWORD = "admin"
    REALM_NAME = "research"

    print("=" * 50)
    print("Keycloak Research Realm Setup")
    print("=" * 50)
    print(f"Keycloak URL: {KEYCLOAK_URL}")
    print(f"Realm: {REALM_NAME}")
    print()

    # Initialize admin client
    admin = KeycloakAdmin(KEYCLOAK_URL, ADMIN_USER, ADMIN_PASSWORD)
    admin.get_admin_token()

    # Create realm
    if not admin.create_realm(REALM_NAME):
        print("Failed to create realm")
        sys.exit(1)

    # Create user-client (for OAuth2 authorization code flow)
    user_client_config = {
        "clientId": "user-client",
        "name": "User Application Client",
        "description": "Client for user authentication and consent flow",
        "enabled": True,
        "clientAuthenticatorType": "client-secret",
        "secret": "user-client-secret",
        "redirectUris": [
            "http://localhost:8080/callback",
            "http://localhost:*"
        ],
        "webOrigins": ["+"],
        "protocol": "openid-connect",
        "publicClient": False,
        "standardFlowEnabled": True,
        "directAccessGrantsEnabled": True,
        "serviceAccountsEnabled": False,
        "authorizationServicesEnabled": False,
        "attributes": {
            "oauth2.device.authorization.grant.enabled": "false",
            "oidc.ciba.grant.enabled": "false",
        },
        "defaultClientScopes": ["web-origins", "acr", "profile", "roles", "email"],
        "optionalClientScopes": ["address", "phone", "offline_access", "microprofile-jwt"]
    }

    user_client_id = admin.create_client(REALM_NAME, user_client_config)
    if not user_client_id:
        print("Failed to create user-client")
        sys.exit(1)

    # Create service-client (for token exchange)
    service_client_config = {
        "clientId": "service-client",
        "name": "Service Client",
        "description": "Service that exchanges tokens to act on behalf of users",
        "enabled": True,
        "clientAuthenticatorType": "client-secret",
        "secret": "service-client-secret",
        "redirectUris": [],
        "webOrigins": [],
        "protocol": "openid-connect",
        "publicClient": False,
        "standardFlowEnabled": False,
        "directAccessGrantsEnabled": False,
        "serviceAccountsEnabled": True,
        "authorizationServicesEnabled": False,
        "attributes": {
            "oauth2.device.authorization.grant.enabled": "false",
            "oidc.ciba.grant.enabled": "false",
            "client.standard.token.exchange.enabled": "true",
            "standard.token.exchange.enabled": "true",
        },
        "defaultClientScopes": ["web-origins", "acr", "profile", "roles", "email"],
        "optionalClientScopes": ["address", "phone", "offline_access", "microprofile-jwt"]
    }

    service_client_id = admin.create_client(REALM_NAME, service_client_config)
    if not service_client_id:
        print("Failed to create service-client")
        sys.exit(1)

    # Add service-client to user-client's audience
    # This allows tokens from user-client to be exchanged by service-client
    admin.add_audience_mapper(REALM_NAME, user_client_id, "service-client")

    # Create demo users
    demo_users = [
        ("alice", "password", "alice@example.com", "Alice", "Researcher"),
        ("bob", "password", "bob@example.com", "Bob", "Developer"),
    ]

    for username, password, email, first_name, last_name in demo_users:
        admin.create_user(REALM_NAME, username, password, email, first_name, last_name)

    # Display summary
    print()
    print("=" * 50)
    print("Configuration Summary")
    print("=" * 50)
    print(f"Keycloak Admin Console: {KEYCLOAK_URL}/admin")
    print(f"  Username: {ADMIN_USER}")
    print(f"  Password: {ADMIN_PASSWORD}")
    print()
    print(f"Realm: {REALM_NAME}")
    print()
    print("Clients:")
    print(f"  user-client:")
    print(f"    Client ID: user-client")
    print(f"    Client Secret: user-client-secret")
    print(f"    Purpose: User authentication via OAuth2 authorization code flow")
    print()
    print(f"  service-client:")
    print(f"    Client ID: service-client")
    print(f"    Client Secret: service-client-secret")
    print(f"    Purpose: Token exchange to act on behalf of users")
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
    print("=" * 50)
    print("Setup Complete!")
    print("=" * 50)


if __name__ == "__main__":
    main()
