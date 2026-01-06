#!/bin/bash

# Configure Token Exchange Permissions in Keycloak
# This script sets up fine-grained permissions for OAuth2 token exchange

set -e

KEYCLOAK_URL="${KEYCLOAK_URL:-http://localhost:30080}"
REALM="agent-demo"
ADMIN_USER="admin"
ADMIN_PASSWORD="admin"

echo "==========================================="
echo "Configuring Token Exchange Permissions"
echo "==========================================="

# Get admin token
echo "Obtaining admin token..."
TOKEN_RESPONSE=$(curl -s -X POST "$KEYCLOAK_URL/realms/master/protocol/openid-connect/token" \
    -H "Content-Type: application/x-www-form-urlencoded" \
    -d "username=$ADMIN_USER" \
    -d "password=$ADMIN_PASSWORD" \
    -d 'grant_type=password' \
    -d 'client_id=admin-cli')

TOKEN=$(echo $TOKEN_RESPONSE | jq -r '.access_token')

if [ "$TOKEN" == "null" ] || [ -z "$TOKEN" ]; then
    echo "Error: Could not obtain admin token"
    exit 1
fi

echo "✓ Admin token obtained"

# Get client IDs
echo "Getting client IDs..."
AGENT_CLIENT_UUID=$(curl -s -X GET "$KEYCLOAK_URL/admin/realms/$REALM/clients?clientId=oauth-agent-client" \
    -H "Authorization: Bearer $TOKEN" | jq -r '.[0].id')

CONSENT_CLIENT_UUID=$(curl -s -X GET "$KEYCLOAK_URL/admin/realms/$REALM/clients?clientId=oauth-agent" \
    -H "Authorization: Bearer $TOKEN" | jq -r '.[0].id')

echo "  Agent client ID: $AGENT_CLIENT_UUID"
echo "  Consent UI client ID: $CONSENT_CLIENT_UUID"

# Enable fine-grained permissions on the consent UI client (oauth-agent)
echo "Enabling permissions on oauth-agent client..."
curl -s -X PUT "$KEYCLOAK_URL/admin/realms/$REALM/clients/$CONSENT_CLIENT_UUID/management/permissions" \
    -H "Authorization: Bearer $TOKEN" \
    -H "Content-Type: application/json" \
    -d '{"enabled": true}'

echo "✓ Permissions enabled"

# Get the permission resource ID for token-exchange
echo "Getting token-exchange permission resource..."
sleep 2  # Give Keycloak time to create permission resources

PERMISSION_RESOURCE=$(curl -s -X GET "$KEYCLOAK_URL/admin/realms/$REALM/clients/$CONSENT_CLIENT_UUID/management/permissions" \
    -H "Authorization: Bearer $TOKEN" | jq -r '.scopePermissions."token-exchange"')

if [ "$PERMISSION_RESOURCE" == "null" ] || [ -z "$PERMISSION_RESOURCE" ]; then
    echo "! Could not get token-exchange permission resource automatically"
    echo "  You may need to configure this manually in the Keycloak admin console:"
    echo "  1. Go to Clients > oauth-agent > Permissions tab"
    echo "  2. Enable permissions if not enabled"
    echo "  3. Click on 'token-exchange' permission"
    echo "  4. Create a policy for oauth-agent-client"
    echo "  5. Add the policy to the token-exchange permission"
    exit 1
fi

echo "  Permission resource ID: $PERMISSION_RESOURCE"

# Create a client policy for oauth-agent-client
echo "Creating client policy for oauth-agent-client..."
POLICY_JSON=$(cat <<EOF
{
  "type": "client",
  "logic": "POSITIVE",
  "decisionStrategy": "UNANIMOUS",
  "name": "oauth-agent-client-policy",
  "clients": ["$AGENT_CLIENT_UUID"]
}
EOF
)

# Create policy in the authorization server for oauth-agent client
POLICY_RESPONSE=$(curl -s -X POST "$KEYCLOAK_URL/admin/realms/$REALM/clients/$CONSENT_CLIENT_UUID/authz/resource-server/policy/client" \
    -H "Authorization: Bearer $TOKEN" \
    -H "Content-Type: application/json" \
    -d "$POLICY_JSON")

POLICY_ID=$(echo $POLICY_RESPONSE | jq -r '.id')

if [ "$POLICY_ID" == "null" ] || [ -z "$POLICY_ID" ]; then
    echo "! Could not create policy (may already exist)"
    # Try to get existing policy
    POLICY_ID=$(curl -s -X GET "$KEYCLOAK_URL/admin/realms/$REALM/clients/$CONSENT_CLIENT_UUID/authz/resource-server/policy?name=oauth-agent-client-policy" \
        -H "Authorization: Bearer $TOKEN" | jq -r '.[0].id')
fi

echo "  Policy ID: $POLICY_ID"

# Update the token-exchange permission to use this policy
echo "Updating token-exchange permission..."
PERMISSION_UPDATE=$(cat <<EOF
{
  "policies": ["$POLICY_ID"]
}
EOF
)

curl -s -X PUT "$KEYCLOAK_URL/admin/realms/$REALM/clients/$CONSENT_CLIENT_UUID/authz/resource-server/permission/scope/$PERMISSION_RESOURCE" \
    -H "Authorization: Bearer $TOKEN" \
    -H "Content-Type: application/json" \
    -d "$PERMISSION_UPDATE"

echo "✓ Token exchange permission configured"
echo ""
echo "==========================================="
echo "Configuration Complete!"
echo "==========================================="
echo "The oauth-agent-client should now be able to exchange tokens from oauth-agent"
