# OAuth Agent - User Delegation via OAuth2

An experimental agent system exploring OAuth2-based user delegation and impersonation.

## Overview

This project investigates how agents can receive delegated permissions from users through OAuth2 consent flows. Unlike the `devoops` agent which uses static ServiceAccount permissions, this agent:

- Has its own OAuth2 client identity in Keycloak
- Receives user consent to act on their behalf
- Uses delegated access tokens for impersonation
- Allows users to revoke agent access ("kick" the agent)

## Architecture

```
┌─────────┐      ┌──────────────┐      ┌─────────┐
│  User   │─────▶│  Consent UI  │─────▶│Keycloak │
└─────────┘      └──────────────┘      └─────────┘
                        │                    │
                        │ stores tokens      │ validates
                        ▼                    ▼
                   ┌─────────┐          ┌──────────┐
                   │  Agent  │─────────▶│Demo API  │
                   └─────────┘          └──────────┘
                        (uses delegated tokens)
```

### Components

1. **Keycloak**: Identity provider and authorization server (shared infrastructure)
2. **Consent UI**: Web interface for OAuth2 authorization flow
3. **Agent**: Long-lived process that acts with delegated permissions
4. **Demo Service**: Example API that validates OAuth2 tokens

**Note**: This experiment uses the shared Keycloak instance from [../shared-infra/keycloak](../shared-infra/keycloak) with its own dedicated realm (`agent-demo`).

## Key Concepts

### Agent Identity
The agent is registered as a confidential OAuth2 client in Keycloak with its own client ID and secret.

### User Delegation
Users authenticate with Keycloak and grant the agent permission to act on their behalf. The agent receives:
- Access tokens (short-lived, for API calls)
- Refresh tokens (long-lived, to obtain new access tokens)

### Impersonation
When the agent makes API calls, it includes the user's access token, allowing it to act as that user.

### Revocation
Users can revoke the agent's access at any time through the consent UI or Keycloak admin interface.

## Quick Start

See [DEPLOYMENT.md](DEPLOYMENT.md) for detailed step-by-step instructions.

### TL;DR

```bash
cd oauth-agent

# 1. Deploy shared Keycloak infrastructure (if not already deployed)
kubectl apply -k ../shared-infra/keycloak/
kubectl wait -n keycloak --for=condition=ready pod -l app=keycloak --timeout=300s

# 2. Deploy oauth-agent namespace
kubectl apply -f k8s/namespace.yaml

# 3. Configure Keycloak realm (creates realm, clients, and demo users)
./scripts/setup-keycloak.sh

# 4. Build images
docker build -f demo-service/Dockerfile -t oauth-demo-service:latest demo-service/
docker build -f Dockerfile.ui -t oauth-consent-ui:latest .
docker build -f Dockerfile.agent -t oauth-agent:latest .

# If using kind:
kind load docker-image oauth-demo-service:latest oauth-consent-ui:latest oauth-agent:latest

# 5. Configure secrets
cp k8s/ui/secret.env.example k8s/ui/secret.env
# Edit k8s/ui/secret.env with your Anthropic API key

# 6. Deploy all services
kubectl apply -k k8s/demo-service/
kubectl apply -k k8s/ui/

# 7. Complete OAuth flow
# Open http://localhost:30800
# Log in as: alice / password
# Grant permissions to agent

# 8. Deploy and watch the agent
kubectl apply -k k8s/agent/
kubectl logs -n oauth-agent -f -l app=oauth-agent
```

### What You'll See

1. **Consent Flow**: User authenticates via Keycloak and grants agent permission
2. **Token Management**: Agent fetches and refreshes OAuth2 tokens automatically
3. **Impersonation**: Agent calls APIs using the user's delegated token
4. **Revocation**: User can "kick" the agent by revoking tokens

### Default Configuration

- **Keycloak Admin**: <http://localhost:30080/admin> (admin/admin)
- **Consent UI**: <http://localhost:30800>
- **Demo API**: <http://localhost:30500>
- **Demo Users**: alice/password, bob/password
- **Agent Mission**: "Check my identity and list my tasks"

## Future Enhancements

- **Token Subscoping**: Use OAuth2 token exchange to create limited-scope tokens
- **Time-Limited Delegation**: Automatic token expiration after a set period
- **Per-Mission Scopes**: Grant different permissions for different agent missions
- **Audit Logging**: Track all actions performed with delegated tokens

## Security Considerations

- Agent client secret must be protected (stored in Kubernetes Secret)
- Tokens are stored securely and never logged
- Users should understand what permissions they're granting
- Regular token rotation via refresh mechanism
- All agent actions should be auditable

## Project Status

Experimental - exploring OAuth2 delegation patterns for agent systems.
