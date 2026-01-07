# Devoops - Kubernetes DevOps Agent

A prompt-driven agent that runs inside a Kubernetes cluster and can perform DevOps tasks on behalf of users.

## Overview

Devoops is an experimental agent that explores the concept of long-lived agents with delegated permissions. It runs as a pod in a Kubernetes cluster, uses its own ServiceAccount identity, and can execute DevOps tasks based on natural language mission prompts.

## Architecture

- **Runtime**: Python container running in Kubernetes
- **Identity**: Kubernetes ServiceAccount with RBAC permissions
- **Intelligence**: Claude API with tool calling
- **Scope**: Single cluster (in-cluster operations only)
- **Interface**: Web UI for mission submission and monitoring

## Features

The agent can:
- List and inspect pods, deployments, and other resources
- Retrieve logs from pods
- Scale deployments
- Investigate cluster issues
- Execute multi-step DevOps workflows based on natural language prompts

## Mission-Based Operation

Give the agent a mission like:
- "Check if there are any crashlooping pods in the default namespace and investigate why"
- "Scale the nginx deployment to 3 replicas"
- "Find all pods using more than 500Mi of memory"
- "Deploy a simple nginx web server with a Service and test it"

The agent uses Claude's reasoning to break down the mission and execute appropriate Kubernetes operations.

## Quick Start

### Prerequisites

- Python 3.11+
- A Kubernetes cluster (Docker Desktop recommended)
- Anthropic API key
- Shared Keycloak infrastructure (for authentication)

### Deploy to Kubernetes (Recommended)

1. **Deploy shared Keycloak infrastructure** (if not already deployed):

```bash
# From repository root
kubectl apply -k shared-infra/keycloak/

# Wait for Keycloak to be ready
kubectl wait -n keycloak --for=condition=ready pod -l app=keycloak --timeout=300s
```

2. **Set up Keycloak realm for devoops:**

```bash
cd devoops
python3 scripts/setup_realm.py
```

This creates:
- Realm: `devoops`
- Client: `devoops-ui-client`
- Demo users: `alice/password`, `bob/password`

3. **Build the container images:**

```bash
# Build agent image
docker build -t devoops:latest .

# Build UI image
docker build -t devoops-ui:latest -f Dockerfile.ui .
```

Note: For Docker Desktop, these images are automatically available. For kind/minikube, you'll need to load them.

4. **Configure secrets:**

```bash
# Agent API key
cp k8s/agent/secret.env.example k8s/agent/secret.env
# Edit k8s/agent/secret.env and add your Anthropic API key

# UI OAuth2 secrets
cp k8s/ui/secret.env.example k8s/ui/secret.env
# Edit k8s/ui/secret.env if needed (defaults work for demo)
```

5. **Deploy:**

```bash
kubectl apply -k k8s/
```

6. **Access the Mission Control UI:**

Open your browser to [http://localhost:30900](http://localhost:30900)

You'll be redirected to Keycloak for authentication. Login with:
- **Username**: `alice` or `bob`
- **Password**: `password`

After authentication, the UI allows you to:
- Submit missions with a simple web form
- View real-time logs as the agent works
- See mission results when complete
- Track mission history

7. **Watch the agent logs (optional):**

```bash
kubectl logs -n devoops -f deployment/devoops-agent
```

8. **Clean up:**

```bash
kubectl delete -k k8s/
```

### Local Development (CLI Mode)

Test the agent locally without Kubernetes (it will use your kubeconfig):

```bash
cd devoops
pip install -e .
export ANTHROPIC_API_KEY="your-api-key"
export MISSION="List all pods in the default namespace"
python -m devoops
```

Note: This runs in CLI mode (single mission, then exits). For the web UI and mission queue, deploy to Kubernetes.

## Authentication

The Mission Control UI requires authentication via the shared Keycloak instance. This ensures only authorized users can submit missions to the agent.

### Demo Users

For development and testing, two demo users are created:
- `alice / password`
- `bob / password`

### OAuth2 Flow

The UI uses OAuth2 Authorization Code Flow:
1. User visits Mission Control UI
2. Redirected to Keycloak login page
3. After successful authentication, redirected back to UI
4. Session established - user can now submit missions

### Keycloak Realm

The devoops realm (`devoops`) is isolated from other experiments. Each experiment has its own realm in the shared Keycloak instance for security and organization.

## Security Considerations

⚠️ This agent has elevated permissions in your cluster. The RBAC configuration defines what it can and cannot do. Review [k8s/rbac.yaml](k8s/rbac.yaml) carefully before deployment.

⚠️ The demo uses development credentials and secrets. For production use:
- Change all secrets in `k8s/agent/secret.env` and `k8s/ui/secret.env`
- Use proper user management in Keycloak
- Enable HTTPS/TLS for all services
- Review and tighten RBAC permissions

## Project Status

Experimental - exploring agent identity and delegation patterns.
