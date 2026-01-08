# Devoops - Agent Instructions

This document provides instructions for AI agents working on the devoops project.

## Project Structure

```
devoops/
├── devoops/                 # Python agent package
│   ├── __main__.py          # Entry point
│   ├── agent.py             # Main agent logic, Mission class, Flask app
│   ├── k8s_tools.py         # Kubernetes tools (list_pods, apply_manifest, etc.)
│   └── test_tools.py        # Testing tools (http_request, exec_in_pod, etc.)
├── ui/                      # Flask OAuth2 backend
│   └── app.py               # OAuth2 flow, API proxy routes
├── ui-react/                # React frontend
│   └── src/
│       ├── App.tsx          # Router setup
│       ├── api/client.ts    # API client
│       ├── components/      # Reusable components
│       ├── pages/           # Page components
│       └── types/           # TypeScript types
├── k8s/                     # Kubernetes manifests
│   ├── namespace.yaml
│   ├── serviceaccount.yaml
│   ├── rbac.yaml
│   ├── agent/               # Agent deployment
│   └── ui-react/            # UI deployment
├── scripts/
│   └── setup_realm.py       # Keycloak realm setup
├── Dockerfile               # Agent container
├── Dockerfile.ui            # UI backend container
└── pyproject.toml           # Python dependencies
```

## Build and Deploy

### Prerequisites

Ensure shared Keycloak infrastructure is running:

```bash
kubectl get pods -n keycloak
```

If not running, deploy it:

```bash
kubectl apply -k shared-infra/keycloak/
kubectl wait -n keycloak --for=condition=ready pod -l app=keycloak --timeout=300s
```

### Building Images

Build all three container images from the `devoops/` directory:

```bash
# Agent image
docker build -t devoops:latest .

# UI backend image
docker build -t devoops-ui:latest -f Dockerfile.ui .

# UI frontend image
docker build -t devoops-ui-react:latest -f ui-react/Dockerfile ui-react/
```

### Deploying

Deploy all resources:

```bash
kubectl apply -k k8s/
```

### Rolling Out Changes

After rebuilding an image, restart the relevant deployment:

```bash
# Agent changes
kubectl rollout restart -n devoops deploy/devoops-agent

# UI backend or frontend changes
kubectl rollout restart -n devoops deploy/devoops-ui-react
```

Watch rollout status:

```bash
kubectl rollout status -n devoops deploy/devoops-agent
kubectl rollout status -n devoops deploy/devoops-ui-react
```

### Viewing Logs

```bash
# Agent logs
kubectl logs -n devoops -f deploy/devoops-agent

# UI backend logs
kubectl logs -n devoops -f deploy/devoops-ui-react -c backend

# UI frontend (nginx) logs
kubectl logs -n devoops -f deploy/devoops-ui-react -c frontend
```

### Testing the Agent API Directly

```bash
# Health check
kubectl exec -n devoops deploy/devoops-agent -- curl -s http://localhost:5000/health

# List missions
kubectl exec -n devoops deploy/devoops-agent -- curl -s http://localhost:5000/api/missions
```

## Key Files Reference

### Agent Core

- [agent.py](devoops/agent.py) - Mission class, DevoopsAgent, Flask endpoints, system prompt
- [k8s_tools.py](devoops/k8s_tools.py) - READ_ONLY_TOOLS and MUTATING_TOOLS definitions
- [test_tools.py](devoops/test_tools.py) - TESTING_TOOLS for verification

### UI Backend

- [ui/app.py](ui/app.py) - OAuth2 flow, session management, API proxy

### UI Frontend

- [App.tsx](ui-react/src/App.tsx) - Route definitions
- [client.ts](ui-react/src/api/client.ts) - API client methods
- [mission.ts](ui-react/src/types/mission.ts) - TypeScript types
- [MissionDetailPage.tsx](ui-react/src/pages/MissionDetailPage.tsx) - Mission view with approval/clarification
- [HomePage.tsx](ui-react/src/pages/HomePage.tsx) - Mission list and submission

### Kubernetes Resources

- [k8s/rbac.yaml](k8s/rbac.yaml) - Agent RBAC permissions
- [k8s/agent/deployment.yaml](k8s/agent/deployment.yaml) - Agent pod spec
- [k8s/ui-react/deployment.yaml](k8s/ui-react/deployment.yaml) - UI pod spec (backend + frontend containers)

## Common Tasks

### Adding a New Tool

1. Define the tool function in `k8s_tools.py` or `test_tools.py`
2. Add tool definition to appropriate list (READ_ONLY_TOOLS or MUTATING_TOOLS)
3. Rebuild and redeploy agent

### Modifying the System Prompt

Edit the `SYSTEM_PROMPT` constant in [agent.py](devoops/agent.py), then rebuild and redeploy.

### Adding New API Endpoints

1. Add Flask route in [agent.py](devoops/agent.py)
2. Add proxy route in [ui/app.py](ui/app.py)
3. Add client method in [client.ts](ui-react/src/api/client.ts)
4. Rebuild and redeploy all affected services

### Modifying UI Components

1. Edit React components in `ui-react/src/`
2. Rebuild frontend: `docker build -t devoops-ui-react:latest -f ui-react/Dockerfile ui-react/`
3. Redeploy: `kubectl rollout restart -n devoops deploy/devoops-ui-react`

## Environment Variables

### Agent (devoops-agent deployment)

- `OPENAI_API_KEY` - API key (from k8s/agent/secret.env)
- `MODE=server` - Run as HTTP server (not CLI)

### UI Backend (devoops-ui-react deployment, backend container)

- `AGENT_URL=http://devoops-agent:5000` - Agent service URL
- `KEYCLOAK_URL` - Internal Keycloak URL
- `KEYCLOAK_PUBLIC_URL` - Public Keycloak URL for browser redirects
- `CLIENT_ID`, `CLIENT_SECRET` - OAuth2 credentials
- `SESSION_SECRET` - Flask session key

## Access URLs

- Mission Control UI: http://localhost:30901
- Keycloak Admin: http://localhost:30080 (admin/admin)
- Agent API (internal): http://devoops-agent:5000

## Demo Users

- alice / password
- bob / password
