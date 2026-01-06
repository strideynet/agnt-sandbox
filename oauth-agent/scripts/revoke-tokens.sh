#!/bin/bash

set -e

# Configuration
KEYCLOAK_URL="${KEYCLOAK_URL:-http://localhost:30080}"
ADMIN_USER="${KEYCLOAK_ADMIN:-admin}"
ADMIN_PASSWORD="${KEYCLOAK_ADMIN_PASSWORD:-admin}"
REALM="agent-demo"
USERNAME="$1"

if [ -z "$USERNAME" ]; then
    echo "Usage: $0 <username>"
    echo ""
    echo "Revoke all tokens for a specific user, effectively 'kicking' the agent."
    echo ""
    echo "Example: $0 alice"
    exit 1
fi

echo "========================================="
echo "Revoking Agent Access for User: $USERNAME"
echo "========================================="

# Get admin token
echo "Obtaining admin token..."
TOKEN=$(curl -s -X POST "$KEYCLOAK_URL/realms/master/protocol/openid-connect/token" \
    -H "Content-Type: application/x-www-form-urlencoded" \
    -d "username=$ADMIN_USER" \
    -d "password=$ADMIN_PASSWORD" \
    -d "grant_type=password" \
    -d "client_id=admin-cli" | jq -r '.access_token')

if [ "$TOKEN" == "null" ] || [ -z "$TOKEN" ]; then
    echo "Error: Failed to obtain admin token"
    exit 1
fi

# Get user ID
echo "Looking up user: $USERNAME..."
USER_ID=$(curl -s -X GET "$KEYCLOAK_URL/admin/realms/$REALM/users?username=$USERNAME" \
    -H "Authorization: Bearer $TOKEN" | jq -r '.[0].id')

if [ "$USER_ID" == "null" ] || [ -z "$USER_ID" ]; then
    echo "Error: User '$USERNAME' not found"
    exit 1
fi

echo "Found user ID: $USER_ID"

# Revoke user sessions (this invalidates all tokens)
echo "Revoking all sessions for user..."
RESPONSE=$(curl -s -w "\n%{http_code}" -X POST \
    "$KEYCLOAK_URL/admin/realms/$REALM/users/$USER_ID/logout" \
    -H "Authorization: Bearer $TOKEN")

HTTP_CODE=$(echo "$RESPONSE" | tail -n1)

if [ "$HTTP_CODE" == "204" ] || [ "$HTTP_CODE" == "200" ]; then
    echo "✓ Successfully revoked all sessions for $USERNAME"
    echo ""
    echo "The agent can no longer act on behalf of $USERNAME."
    echo "User will need to consent again to re-delegate access."
else
    echo "Error revoking sessions. HTTP code: $HTTP_CODE"
    echo "$RESPONSE"
    exit 1
fi

echo ""
echo "========================================="
echo "Revocation Complete!"
echo "========================================="
