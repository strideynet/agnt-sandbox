#!/bin/bash

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo "========================================="
echo "OAuth Agent - End-to-End Test"
echo "========================================="
echo ""

# Configuration
NAMESPACE="oauth-agent"
KEYCLOAK_URL="${KEYCLOAK_URL:-http://localhost:30080}"
CONSENT_UI_URL="${CONSENT_UI_URL:-http://localhost:30800}"
DEMO_API_URL="${DEMO_API_URL:-http://localhost:30500}"

# Test 1: Check all pods are running
echo "Test 1: Checking pod status..."
PODS=$(kubectl get pods -n $NAMESPACE --no-headers 2>/dev/null | wc -l || echo "0")

if [ "$PODS" -eq 0 ]; then
    echo -e "${RED}✗ No pods found in namespace $NAMESPACE${NC}"
    echo "  Run: kubectl apply -k oauth-agent/k8s/"
    exit 1
fi

echo -e "${GREEN}✓ Found $PODS pods in namespace $NAMESPACE${NC}"
kubectl get pods -n $NAMESPACE

# Test 2: Check Keycloak health
echo ""
echo "Test 2: Checking Keycloak health..."
if curl -s -f "$KEYCLOAK_URL/realms/master" > /dev/null 2>&1; then
    echo -e "${GREEN}✓ Keycloak is healthy${NC}"
else
    echo -e "${RED}✗ Keycloak health check failed${NC}"
    echo "  URL: $KEYCLOAK_URL/realms/master"
    exit 1
fi

# Test 3: Check Consent UI health
echo ""
echo "Test 3: Checking Consent UI health..."
if curl -s -f "$CONSENT_UI_URL/health" > /dev/null 2>&1; then
    echo -e "${GREEN}✓ Consent UI is healthy${NC}"
else
    echo -e "${RED}✗ Consent UI health check failed${NC}"
    echo "  URL: $CONSENT_UI_URL/health"
    exit 1
fi

# Test 4: Check Demo API health
echo ""
echo "Test 4: Checking Demo API health..."
if curl -s -f "$DEMO_API_URL/health" > /dev/null 2>&1; then
    echo -e "${GREEN}✓ Demo API is healthy${NC}"
else
    echo -e "${RED}✗ Demo API health check failed${NC}"
    echo "  URL: $DEMO_API_URL/health"
    exit 1
fi

# Test 5: Check if realm exists
echo ""
echo "Test 5: Checking Keycloak realm configuration..."
REALM_CHECK=$(curl -s "$KEYCLOAK_URL/realms/agent-demo" 2>/dev/null | grep -c "agent-demo" || echo "0")

if [ "$REALM_CHECK" -gt 0 ]; then
    echo -e "${GREEN}✓ Realm 'agent-demo' is configured${NC}"
else
    echo -e "${YELLOW}! Realm 'agent-demo' not found${NC}"
    echo "  Run: ./scripts/setup-keycloak.sh"
fi

# Test 6: Check for user delegation
echo ""
echo "Test 6: Checking for user delegations..."
ALICE_TOKEN=$(curl -s "$CONSENT_UI_URL/api/token/alice" 2>/dev/null)

if echo "$ALICE_TOKEN" | grep -q "access_token"; then
    echo -e "${GREEN}✓ User 'alice' has granted delegation${NC}"
else
    echo -e "${YELLOW}! User 'alice' has not completed OAuth flow${NC}"
    echo "  Go to: $CONSENT_UI_URL"
    echo "  Log in as: alice / password"
fi

BOB_TOKEN=$(curl -s "$CONSENT_UI_URL/api/token/bob" 2>/dev/null)

if echo "$BOB_TOKEN" | grep -q "access_token"; then
    echo -e "${GREEN}✓ User 'bob' has granted delegation${NC}"
else
    echo -e "${YELLOW}! User 'bob' has not completed OAuth flow${NC}"
fi

# Test 7: Test Demo API without token (should fail)
echo ""
echo "Test 7: Testing Demo API without token (should return 401)..."
RESPONSE=$(curl -s -w "\n%{http_code}" "$DEMO_API_URL/api/whoami" 2>/dev/null)
HTTP_CODE=$(echo "$RESPONSE" | tail -n1)

if [ "$HTTP_CODE" == "401" ]; then
    echo -e "${GREEN}✓ Demo API correctly rejects requests without token${NC}"
else
    echo -e "${RED}✗ Unexpected HTTP code: $HTTP_CODE (expected 401)${NC}"
fi

# Test 8: Test Demo API with token (if alice has delegation)
if echo "$ALICE_TOKEN" | grep -q "access_token"; then
    echo ""
    echo "Test 8: Testing Demo API with alice's token..."
    ACCESS_TOKEN=$(echo "$ALICE_TOKEN" | jq -r '.access_token' 2>/dev/null)

    if [ "$ACCESS_TOKEN" != "null" ] && [ -n "$ACCESS_TOKEN" ]; then
        RESPONSE=$(curl -s -H "Authorization: Bearer $ACCESS_TOKEN" "$DEMO_API_URL/api/whoami" 2>/dev/null)

        if echo "$RESPONSE" | grep -q "alice"; then
            echo -e "${GREEN}✓ Demo API successfully validated alice's token${NC}"
            echo "  Response: $(echo $RESPONSE | jq -r '.message' 2>/dev/null)"
        else
            echo -e "${RED}✗ Token validation failed${NC}"
            echo "  Response: $RESPONSE"
        fi
    fi
fi

# Test 9: Check agent logs
echo ""
echo "Test 9: Checking agent status..."
AGENT_POD=$(kubectl get pods -n $NAMESPACE -l app=oauth-agent -o jsonpath='{.items[0].metadata.name}' 2>/dev/null || echo "")

if [ -n "$AGENT_POD" ]; then
    echo -e "${GREEN}✓ Agent pod found: $AGENT_POD${NC}"
    echo ""
    echo "Recent agent logs:"
    kubectl logs -n $NAMESPACE "$AGENT_POD" --tail=20 2>/dev/null || echo "  (no logs yet)"
else
    echo -e "${YELLOW}! Agent pod not found${NC}"
    echo "  Run: kubectl apply -k oauth-agent/k8s/agent/"
fi

# Summary
echo ""
echo "========================================="
echo "Test Summary"
echo "========================================="
echo ""
echo "Access Points:"
echo "  - Keycloak Admin: $KEYCLOAK_URL/admin (admin/admin)"
echo "  - Consent UI: $CONSENT_UI_URL"
echo "  - Demo API: $DEMO_API_URL"
echo ""
echo "Next Steps:"
echo "  1. Grant delegation: $CONSENT_UI_URL"
echo "  2. Watch agent logs: kubectl logs -n oauth-agent -l app=oauth-agent -f"
echo "  3. Revoke access: ./scripts/revoke-tokens.sh <username>"
echo ""
echo "========================================="
