# Quick Start - OAuth Agent

Get up and running in 10 minutes.

## Prerequisites

- Kubernetes cluster running (kind, minikube, or cloud)
- Docker installed
- `kubectl` configured
- `jq` installed
- Anthropic API key

## 1. Deploy Infrastructure (2 minutes)

```bash
cd oauth-agent

# Deploy namespace and Keycloak
kubectl apply -f k8s/namespace.yaml
kubectl apply -k k8s/keycloak/

# Wait for Keycloak (takes 1-2 minutes)
kubectl wait -n oauth-agent --for=condition=ready pod -l app=keycloak --timeout=300s
```

## 2. Configure Keycloak (30 seconds)

```bash
# Create realm, OAuth client, and demo users
./scripts/setup-keycloak.sh
```

**Output**: You'll see realm configuration with demo users (alice/password, bob/password)

## 3. Build & Load Images (2 minutes)

```bash
# Build all images
docker build -f demo-service/Dockerfile -t oauth-demo-service:latest demo-service/
docker build -f Dockerfile.ui -t oauth-consent-ui:latest .
docker build -f Dockerfile.agent -t oauth-agent:latest .

# For kind:
kind load docker-image oauth-demo-service:latest oauth-consent-ui:latest oauth-agent:latest

# For minikube:
# minikube image load oauth-demo-service:latest oauth-consent-ui:latest oauth-agent:latest
```

## 4. Configure Secrets (1 minute)

```bash
# Copy example
cp k8s/ui/secret.env.example k8s/ui/secret.env

# Edit with your API key
vim k8s/ui/secret.env
# or
# echo "anthropic-api-key=sk-ant-your-key-here" >> k8s/ui/secret.env
```

## 5. Deploy Services (1 minute)

```bash
# Deploy demo API and consent UI
kubectl apply -k k8s/demo-service/
kubectl apply -k k8s/ui/

# Wait for them to be ready
kubectl wait -n oauth-agent --for=condition=ready pod -l app=demo-service --timeout=60s
kubectl wait -n oauth-agent --for=condition=ready pod -l app=consent-ui --timeout=60s
```

## 6. Grant Agent Delegation (1 minute)

Open your browser to the consent UI:

```bash
# Should open automatically
open http://localhost:30800

# Or visit manually: http://localhost:30800
```

**Steps:**
1. Click "Grant Agent Access"
2. Login: `alice` / `password`
3. Approve the consent screen
4. You'll see "Authorization Successful!"

## 7. Deploy & Watch Agent (1 minute)

```bash
# Deploy the agent (configured to act as alice)
kubectl apply -k k8s/agent/

# Watch it work!
kubectl logs -n oauth-agent -f -l app=oauth-agent
```

**What you'll see:**
- Agent fetches token for alice
- Calls Claude API to plan mission
- Uses delegated token to call demo API
- Returns results

## 8. Test Everything

```bash
# Run the test script
./scripts/test-flow.sh
```

## 9. Revoke Access

```bash
# Kick the agent
./scripts/revoke-tokens.sh alice

# Or via UI: http://localhost:30800 → "Revoke Agent Access"
```

## 10. Experiment

### Change the mission

```bash
kubectl edit deployment -n oauth-agent oauth-agent

# Change the MISSION environment variable to something like:
# - "Create a new task called 'Deploy to production'"
# - "List all my tasks and create a summary"
# - "Check my identity and perform a backup action"
```

### Switch to a different user

```bash
# First, grant delegation for bob
open http://localhost:30800
# Login as: bob / password

# Then update the agent
kubectl edit deployment -n oauth-agent oauth-agent
# Change USERNAME from "alice" to "bob"
```

### View logs

```bash
# Agent logs
kubectl logs -n oauth-agent -l app=oauth-agent -f

# Consent UI logs
kubectl logs -n oauth-agent -l app=consent-ui -f

# Demo API logs
kubectl logs -n oauth-agent -l app=demo-service -f

# Keycloak logs
kubectl logs -n oauth-agent -l app=keycloak -f
```

## Troubleshooting

### Keycloak won't start

```bash
# Check PostgreSQL is running
kubectl get pods -n oauth-agent -l app=postgres

# Check logs
kubectl logs -n oauth-agent -l app=keycloak
```

### OAuth flow fails

```bash
# Check redirect URI in deployment
kubectl get deployment -n oauth-agent consent-ui -o yaml | grep REDIRECT_URI

# Should be: http://localhost:30800/callback
```

### Agent can't get token

```bash
# Verify user completed OAuth flow
curl http://localhost:30800/api/token/alice

# Should return JSON with access_token
# If 404: User hasn't granted delegation yet
```

### Token validation fails

```bash
# Test manually
TOKEN=$(curl -s http://localhost:30800/api/token/alice | jq -r '.access_token')
curl -H "Authorization: Bearer $TOKEN" http://localhost:30500/api/whoami
```

## Cleanup

```bash
# Delete everything
kubectl delete namespace oauth-agent
```

## Next Steps

- Read [ARCHITECTURE.md](ARCHITECTURE.md) to understand the system
- Read [DEPLOYMENT.md](DEPLOYMENT.md) for production considerations
- Experiment with token subscoping
- Add audit logging
- Implement proper token storage

## Quick Reference

**URLs:**
- Keycloak: <http://localhost:30080/admin> (admin/admin)
- Consent UI: <http://localhost:30800>
- Demo API: <http://localhost:30500>

**Users:**
- alice / password
- bob / password

**Useful Commands:**
```bash
# Watch all pods
kubectl get pods -n oauth-agent -w

# Follow agent logs
kubectl logs -n oauth-agent -l app=oauth-agent -f

# Restart agent
kubectl rollout restart -n oauth-agent deployment/oauth-agent

# Port forward Keycloak (alternative to NodePort)
kubectl port-forward -n oauth-agent svc/keycloak 8080:8080

# Get all resources
kubectl get all -n oauth-agent
```
