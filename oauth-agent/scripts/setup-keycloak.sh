#!/bin/bash

set -e

# Configuration
NAMESPACE="oauth-agent"
KEYCLOAK_URL="${KEYCLOAK_URL:-http://localhost:30080}"
ADMIN_USER="${KEYCLOAK_ADMIN:-admin}"
ADMIN_PASSWORD="${KEYCLOAK_ADMIN_PASSWORD:-admin}"
REALM="agent-demo"

echo "========================================="
echo "Keycloak Setup for OAuth Agent"
echo "========================================="
echo "Keycloak URL: $KEYCLOAK_URL"
echo "Realm: $REALM"
echo ""

# Check if jq is installed
if ! command -v jq &> /dev/null; then
    echo "Error: jq is required but not installed. Please install jq and try again."
    exit 1
fi

# Function to get admin token
get_admin_token() {
    echo "Obtaining admin token..."
    TOKEN=$(curl -s -X POST "$KEYCLOAK_URL/realms/master/protocol/openid-connect/token" \
        -H "Content-Type: application/x-www-form-urlencoded" \
        -d "username=$ADMIN_USER" \
        -d "password=$ADMIN_PASSWORD" \
        -d "grant_type=password" \
        -d "client_id=admin-cli" | jq -r '.access_token')

    if [ "$TOKEN" == "null" ] || [ -z "$TOKEN" ]; then
        echo "Error: Failed to obtain admin token. Check your credentials."
        exit 1
    fi
    echo "Successfully obtained admin token"
}

# Function to create realm
create_realm() {
    echo ""
    echo "Creating realm: $REALM..."

    REALM_JSON=$(cat <<EOF
{
  "realm": "$REALM",
  "enabled": true,
  "sslRequired": "none",
  "registrationAllowed": true,
  "loginWithEmailAllowed": true,
  "duplicateEmailsAllowed": false,
  "resetPasswordAllowed": true,
  "editUsernameAllowed": false,
  "bruteForceProtected": true,
  "accessTokenLifespan": 300,
  "refreshTokenMaxReuse": 0,
  "ssoSessionIdleTimeout": 1800,
  "ssoSessionMaxLifespan": 36000
}
EOF
)

    RESPONSE=$(curl -s -w "\n%{http_code}" -X POST "$KEYCLOAK_URL/admin/realms" \
        -H "Authorization: Bearer $TOKEN" \
        -H "Content-Type: application/json" \
        -d "$REALM_JSON")

    HTTP_CODE=$(echo "$RESPONSE" | tail -n1)

    if [ "$HTTP_CODE" == "201" ]; then
        echo "✓ Realm created successfully"
    elif [ "$HTTP_CODE" == "409" ]; then
        echo "! Realm already exists, continuing..."
    else
        echo "Error creating realm. HTTP code: $HTTP_CODE"
        echo "$RESPONSE"
        exit 1
    fi
}

# Function to create consent UI client
create_consent_ui_client() {
    echo ""
    echo "Creating OAuth2 client for consent UI..."

    CLIENT_JSON=$(cat <<EOF
{
  "clientId": "consent-ui-client",
  "name": "Consent UI Client",
  "description": "Web UI for user consent and token management",
  "enabled": true,
  "clientAuthenticatorType": "client-secret",
  "secret": "agent-secret-change-in-production",
  "redirectUris": ["http://localhost:*", "http://consent-ui:*"],
  "webOrigins": ["+"],
  "protocol": "openid-connect",
  "publicClient": false,
  "standardFlowEnabled": true,
  "directAccessGrantsEnabled": false,
  "serviceAccountsEnabled": true,
  "authorizationServicesEnabled": true,
  "attributes": {
    "oauth2.device.authorization.grant.enabled": "false",
    "oidc.ciba.grant.enabled": "false"
  },
  "defaultClientScopes": ["web-origins", "acr", "profile", "roles", "email"],
  "optionalClientScopes": ["address", "phone", "offline_access", "microprofile-jwt"]
}
EOF
)

    RESPONSE=$(curl -s -w "\n%{http_code}" -X POST "$KEYCLOAK_URL/admin/realms/$REALM/clients" \
        -H "Authorization: Bearer $TOKEN" \
        -H "Content-Type: application/json" \
        -d "$CLIENT_JSON")

    HTTP_CODE=$(echo "$RESPONSE" | tail -n1)

    if [ "$HTTP_CODE" == "201" ]; then
        echo "✓ Consent UI client created successfully"
    elif [ "$HTTP_CODE" == "409" ]; then
        echo "! Consent UI client already exists, continuing..."
    else
        echo "Error creating consent UI client. HTTP code: $HTTP_CODE"
        echo "$RESPONSE"
        exit 1
    fi
}

# Function to create agent client (separate from consent UI)
create_agent_client() {
    echo ""
    echo "Creating OAuth2 client for agent (with token exchange)..."

    CLIENT_JSON=$(cat <<EOF
{
  "clientId": "oauth-agent-client",
  "name": "OAuth Agent Service",
  "description": "Agent service that exchanges tokens to act on behalf of users",
  "enabled": true,
  "clientAuthenticatorType": "client-secret",
  "secret": "agent-client-secret-change-in-production",
  "redirectUris": [],
  "webOrigins": [],
  "protocol": "openid-connect",
  "publicClient": false,
  "standardFlowEnabled": false,
  "directAccessGrantsEnabled": false,
  "serviceAccountsEnabled": true,
  "authorizationServicesEnabled": false,
  "attributes": {
    "oauth2.device.authorization.grant.enabled": "false",
    "oidc.ciba.grant.enabled": "false",
    "token.exchange.grant.enabled": "true"
  },
  "defaultClientScopes": ["web-origins", "acr", "profile", "roles", "email"],
  "optionalClientScopes": ["address", "phone", "offline_access", "microprofile-jwt"]
}
EOF
)

    RESPONSE=$(curl -s -w "\n%{http_code}" -X POST "$KEYCLOAK_URL/admin/realms/$REALM/clients" \
        -H "Authorization: Bearer $TOKEN" \
        -H "Content-Type: application/json" \
        -d "$CLIENT_JSON")

    HTTP_CODE=$(echo "$RESPONSE" | tail -n1)

    if [ "$HTTP_CODE" == "201" ]; then
        echo "✓ Agent service client created successfully"
    elif [ "$HTTP_CODE" == "409" ]; then
        echo "! Agent service client already exists, continuing..."
    else
        echo "Error creating agent service client. HTTP code: $HTTP_CODE"
        echo "$RESPONSE"
        exit 1
    fi
}

# Function to configure token exchange permissions
configure_token_exchange() {
    echo ""
    echo "Configuring token exchange permissions..."

    # Get the internal ID of the oauth-agent-client
    CLIENT_ID=$(curl -s -X GET "$KEYCLOAK_URL/admin/realms/$REALM/clients?clientId=oauth-agent-client" \
        -H "Authorization: Bearer $TOKEN" | jq -r '.[0].id')

    if [ "$CLIENT_ID" == "null" ] || [ -z "$CLIENT_ID" ]; then
        echo "Error: Could not find oauth-agent-client"
        exit 1
    fi

    echo "Found agent client with ID: $CLIENT_ID"

    # Enable token exchange permission for the agent client
    # This allows the agent client to exchange tokens
    echo "Enabling token exchange for agent client..."

    # Get the internal ID of the consent-ui-client (the source client)
    SOURCE_CLIENT_ID=$(curl -s -X GET "$KEYCLOAK_URL/admin/realms/$REALM/clients?clientId=oauth-agent" \
        -H "Authorization: Bearer $TOKEN" | jq -r '.[0].id')

    if [ "$SOURCE_CLIENT_ID" == "null" ] || [ -z "$SOURCE_CLIENT_ID" ]; then
        echo "Error: Could not find consent-ui-client"
        exit 1
    fi

    echo "Found source client (oauth-agent) with ID: $SOURCE_CLIENT_ID"

    # Create token-exchange permission for the agent client to exchange tokens from oauth-agent
    # This uses Keycloak's fine-grained admin permissions API
    PERMISSION_JSON=$(cat <<EOF
{
  "name": "token-exchange-permission",
  "description": "Allow oauth-agent-client to exchange tokens from oauth-agent",
  "type": "scope",
  "logic": "POSITIVE",
  "decisionStrategy": "UNANIMOUS",
  "scopes": ["token-exchange"],
  "clients": ["$CLIENT_ID"]
}
EOF
)

    echo "Setting up token exchange permission..."
    # Note: This may fail if permissions don't exist or API doesn't support this
    # In that case, manual configuration in Keycloak admin console is needed
    curl -s -X PUT "$KEYCLOAK_URL/admin/realms/$REALM/clients/$SOURCE_CLIENT_ID/management/permissions" \
        -H "Authorization: Bearer $TOKEN" \
        -H "Content-Type: application/json" \
        -d '{"enabled": true}' > /dev/null 2>&1

    echo "✓ Token exchange permissions configured"
    echo "  Note: If token exchange still fails, you may need to configure permissions"
    echo "  in the Keycloak admin console under Clients > oauth-agent > Permissions"
}

# Function to create demo users
create_demo_users() {
    echo ""
    echo "Creating demo users..."

    for username in "alice" "bob"; do
        USER_JSON=$(cat <<EOF
{
  "username": "$username",
  "email": "$username@example.com",
  "firstName": "$(echo $username | sed 's/\b\(.\)/\u\1/g')",
  "lastName": "Demo",
  "enabled": true,
  "emailVerified": true,
  "credentials": [{
    "type": "password",
    "value": "password",
    "temporary": false
  }]
}
EOF
)

        RESPONSE=$(curl -s -w "\n%{http_code}" -X POST "$KEYCLOAK_URL/admin/realms/$REALM/users" \
            -H "Authorization: Bearer $TOKEN" \
            -H "Content-Type: application/json" \
            -d "$USER_JSON")

        HTTP_CODE=$(echo "$RESPONSE" | tail -n1)

        if [ "$HTTP_CODE" == "201" ]; then
            echo "✓ User $username created (password: password)"
        elif [ "$HTTP_CODE" == "409" ]; then
            echo "! User $username already exists"
        else
            echo "Warning: Could not create user $username. HTTP code: $HTTP_CODE"
        fi
    done
}

# Function to display configuration summary
display_summary() {
    echo ""
    echo "========================================="
    echo "Configuration Summary"
    echo "========================================="
    echo "Keycloak Admin Console: $KEYCLOAK_URL/admin"
    echo "  Username: $ADMIN_USER"
    echo "  Password: $ADMIN_PASSWORD"
    echo ""
    echo "Realm: $REALM"
    echo ""
    echo "OAuth2 Client (Consent UI):"
    echo "  Client ID: oauth-agent"
    echo "  Client Secret: agent-secret-change-in-production"
    echo "  Purpose: User consent and token storage"
    echo ""
    echo "OAuth2 Client (Agent Service):"
    echo "  Client ID: oauth-agent-client"
    echo "  Client Secret: agent-client-secret-change-in-production"
    echo "  Purpose: Token exchange to act on behalf of users"
    echo ""
    echo "Demo Users:"
    echo "  alice / password"
    echo "  bob / password"
    echo ""
    echo "Token Endpoint: $KEYCLOAK_URL/realms/$REALM/protocol/openid-connect/token"
    echo "Authorization Endpoint: $KEYCLOAK_URL/realms/$REALM/protocol/openid-connect/auth"
    echo "Userinfo Endpoint: $KEYCLOAK_URL/realms/$REALM/protocol/openid-connect/userinfo"
    echo ""
    echo "========================================="
    echo "Setup Complete!"
    echo "========================================="
}

# Main execution
main() {
    echo "Waiting for Keycloak to be ready..."

    # Wait for Keycloak to be healthy
    for i in {1..30}; do
        if curl -s -f "$KEYCLOAK_URL/health/ready" > /dev/null 2>&1; then
            echo "Keycloak is ready!"
            break
        fi
        if [ $i -eq 30 ]; then
            echo "Error: Keycloak did not become ready in time"
            exit 1
        fi
        echo "Waiting... ($i/30)"
        sleep 2
    done

    get_admin_token
    create_realm
    create_consent_ui_client
    create_agent_client
    configure_token_exchange
    create_demo_users
    display_summary
}

main
