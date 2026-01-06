# Deployment Guide - OAuth Agent

Step-by-step guide to deploy and test the OAuth2 delegation experiment.

## Prerequisites

- Kubernetes cluster (kind, minikube, or cloud provider)
- `kubectl` configured and connected to your cluster
- Docker installed for building images
- `jq` installed (for the setup script)
- Anthropic API key

## Architecture Overview

```
User Browser ──┐
               │
               ├─► Consent UI (port 30800)
               │   ├─► OAuth2 Authorization Flow
               │   └─► Token Storage
               │
               ├─► Keycloak (port 30080)
               │   └─► Identity Provider
               │
               └─► Demo Service (port 30500)
                   └─► OAuth2 Token Validation

Agent Pod ────────► Consent UI API ──► Get User Tokens
               └──► Demo Service ────► Act as User
```

## Step 1: Create Namespace

```bash
cd oauth-agent
kubectl apply -f k8s/namespace.yaml
```

Verify:
```bash
kubectl get namespace oauth-agent
```

## Step 2: Deploy Keycloak

Deploy PostgreSQL and Keycloak:

```bash
kubectl apply -k k8s/keycloak/
```

Wait for Keycloak to be ready (this can take 2-3 minutes):

```bash
kubectl wait -n oauth-agent --for=condition=ready pod -l app=keycloak --timeout=300s
```

Check the logs:
```bash
kubectl logs -n oauth-agent -l app=keycloak -f
```

You should see Keycloak start successfully. Access the admin console:
```bash
# If using kind/minikube
open http://localhost:30080/admin

# Or port-forward
kubectl port-forward -n oauth-agent svc/keycloak 8080:8080
```

Admin credentials: `admin` / `admin`

## Step 3: Configure Keycloak Realm

Run the setup script to create the realm, client, and demo users:

```bash
# If using NodePort (kind/minikube)
./scripts/setup-keycloak.sh

# If port-forwarding
KEYCLOAK_URL=http://localhost:8080 ./scripts/setup-keycloak.sh
```

The script will:
- Create realm `agent-demo`
- Create OAuth2 client `oauth-agent` with client secret
- Create demo users `alice` and `bob` (password: `password`)

**Save the configuration output!** You'll need the client secret.

## Step 4: Build Docker Images

### Demo Service

```bash
docker build -f demo-service/Dockerfile -t oauth-demo-service:latest demo-service/
```

### Consent UI

```bash
docker build -f Dockerfile.ui -t oauth-consent-ui:latest .
```

### Agent

```bash
docker build -f Dockerfile.agent -t oauth-agent:latest .
```

### Load Images (for kind/minikube)

If using kind:
```bash
kind load docker-image oauth-demo-service:latest
kind load docker-image oauth-consent-ui:latest
kind load docker-image oauth-agent:latest
```

If using minikube:
```bash
minikube image load oauth-demo-service:latest
minikube image load oauth-consent-ui:latest
minikube image load oauth-agent:latest
```

## Step 5: Configure Secrets

Create the secret configuration file:

```bash
cp k8s/ui/secret.env.example k8s/ui/secret.env
```

Edit `k8s/ui/secret.env` and add:
- Your Anthropic API key
- Client secret from Keycloak (or keep default for dev)
- Random session secret

```bash
# Generate a random session secret
python3 -c "import secrets; print(f'session-secret={secrets.token_hex(32)}')"
```

## Step 6: Deploy Demo Service

```bash
kubectl apply -k k8s/demo-service/
```

Wait for it to be ready:
```bash
kubectl wait -n oauth-agent --for=condition=ready pod -l app=demo-service --timeout=60s
```

Test it (should return 401 since we don't have a token yet):
```bash
curl http://localhost:30500/health
```

## Step 7: Deploy Consent UI

```bash
kubectl apply -k k8s/ui/
```

Wait for it to be ready:
```bash
kubectl wait -n oauth-agent --for=condition=ready pod -l app=consent-ui --timeout=60s
```

Access the UI:
```bash
open http://localhost:30800
```

## Step 8: Grant Agent Delegation

1. Open the Consent UI: http://localhost:30800
2. Click "Grant Agent Access"
3. You'll be redirected to Keycloak
4. Log in as `alice` (password: `password`)
5. Grant the requested permissions
6. You'll be redirected back with a success message

The agent now has an OAuth2 token to act as Alice!

## Step 9: Deploy the Agent

The agent is configured to act as user `alice` by default. Edit the deployment if you want to change this:

```bash
kubectl edit deployment -n oauth-agent oauth-agent
# Change the USERNAME and MISSION environment variables
```

Deploy:
```bash
kubectl apply -k k8s/agent/
```

Watch the agent work:
```bash
kubectl logs -n oauth-agent -l app=oauth-agent -f
```

You should see:
1. Agent starting up
2. Fetching token for user `alice`
3. Executing the mission using Claude
4. Making API calls with the delegated token
5. Returning results

## Step 10: Test Revocation

Revoke Alice's delegation:

**Option 1: Via UI**
- Go to http://localhost:30800
- Click "Revoke Agent Access"

**Option 2: Via Script**
```bash
./scripts/revoke-tokens.sh alice
```

**Option 3: Via Keycloak Admin Console**
- Go to http://localhost:30080/admin
- Navigate to Users → Alice → Sessions
- Click "Sign out" for all sessions

Now restart the agent and watch it fail to get a token:
```bash
kubectl rollout restart -n oauth-agent deployment/oauth-agent
kubectl logs -n oauth-agent -l app=oauth-agent -f
```

## Troubleshooting

### Keycloak won't start
```bash
# Check PostgreSQL
kubectl logs -n oauth-agent -l app=postgres

# Check Keycloak logs
kubectl logs -n oauth-agent -l app=keycloak
```

### Setup script fails
```bash
# Make sure Keycloak is fully ready
kubectl get pods -n oauth-agent

# Try accessing the admin console manually
curl http://localhost:30080/health/ready
```

### OAuth flow fails
```bash
# Check consent UI logs
kubectl logs -n oauth-agent -l app=consent-ui -f

# Check redirect URI matches
# It should be: http://localhost:30800/callback
```

### Agent can't get tokens
```bash
# Verify user completed OAuth flow
curl http://localhost:30800/api/token/alice

# Check consent UI logs
kubectl logs -n oauth-agent -l app=consent-ui
```

### Demo service returns 401
```bash
# Test with a valid token from the consent UI
# After completing OAuth flow, the token is displayed in the UI

# Check demo service logs
kubectl logs -n oauth-agent -l app=demo-service
```

## Cleanup

Remove everything:

```bash
kubectl delete namespace oauth-agent
```

Or just remove the agent:
```bash
kubectl delete -k k8s/agent/
```

## Next Steps

1. **Try different missions**: Edit the `MISSION` env var in the agent deployment
2. **Test with multiple users**: Complete OAuth flow for `bob` and switch the agent to use `bob`
3. **Explore subscoping**: Modify the OAuth scopes to limit what the agent can do
4. **Add audit logging**: Track all actions the agent performs
5. **Implement proper token storage**: Use a database instead of in-memory storage
6. **Add token rotation**: Implement automatic refresh before expiration

## Production Considerations

- [ ] Use proper secrets management (Vault, AWS Secrets Manager, etc.)
- [ ] Enable TLS/HTTPS everywhere
- [ ] Use a real database for token storage
- [ ] Implement proper session management
- [ ] Add audit logging for all agent actions
- [ ] Configure proper Keycloak realm settings (password policies, MFA, etc.)
- [ ] Set up token rotation and automatic refresh
- [ ] Implement rate limiting
- [ ] Add monitoring and alerting
- [ ] Use proper ingress with DNS
