# Devoops - Kubernetes DevOps Agent

A prompt-driven agent that runs inside a Kubernetes cluster and can perform DevOps tasks on behalf of users.

## Overview

Devoops is an experimental agent that explores the concept of long-lived agents with delegated permissions. It runs as a pod in a Kubernetes cluster, uses its own ServiceAccount identity, and can execute DevOps tasks based on natural language mission prompts.

Key concepts:
- **Long-lived agent**: Runs continuously in the cluster, not invoked on-demand
- **Own identity**: Has its own Kubernetes ServiceAccount, separate from users
- **Delegated authority**: Acts on behalf of users within its RBAC permissions
- **Human-in-the-loop**: Requires user approval before executing mutating operations

## Architecture

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                        Kubernetes Cluster                                    │
│                                                                             │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │                      devoops namespace                               │   │
│  │                                                                      │   │
│  │  ┌──────────────────┐         ┌──────────────────────────────────┐  │   │
│  │  │  devoops-agent   │         │      devoops-ui-react            │  │   │
│  │  │                  │         │  ┌────────────┐ ┌─────────────┐  │  │   │
│  │  │  Python Agent    │◄────────│  │  Flask     │ │   Nginx     │  │  │   │
│  │  │  - Claude AI     │  HTTP   │  │  Backend   │ │  (React UI) │  │  │   │
│  │  │  - K8s Tools     │         │  │  :8080     │ │    :80      │  │  │   │
│  │  │    :5000         │         │  └─────┬──────┘ └──────┬──────┘  │  │   │
│  │  └────────┬─────────┘         └────────┼───────────────┼─────────┘  │   │
│  │           │                            │               │            │   │
│  │           │                            │    OAuth2     │            │   │
│  │           ▼                            ▼               │            │   │
│  │  ┌────────────────┐           ┌────────────────┐      │            │   │
│  │  │ Kubernetes API │           │   Keycloak     │◄─────┘            │   │
│  │  │ (via RBAC)     │           │   (shared)     │   Browser         │   │
│  │  └────────────────┘           │   :30080       │   redirects       │   │
│  │                               └────────────────┘                   │   │
│  └──────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
                                      ▲
                                      │ NodePort :30901
                                      │
                               ┌──────┴──────┐
                               │   Browser   │
                               │  (User)     │
                               └─────────────┘
```

### Components

| Component | Purpose | Tech Stack |
|-----------|---------|------------|
| **devoops-agent** | AI agent that executes missions | Python, OpenAI SDK, Kubernetes client |
| **UI Backend** | OAuth2 gateway + API proxy | Python Flask |
| **UI Frontend** | Mission Control web interface | React, TypeScript, Tailwind |
| **Keycloak** | Identity provider (shared infra) | Keycloak |

### Agent Service

The agent is the core component - a long-lived Python process that:

1. **Receives missions** via HTTP API (`POST /api/missions`)
2. **Reasons about tasks** using Claude with tool calling
3. **Executes Kubernetes operations** using its ServiceAccount permissions
4. **Supports human-in-the-loop** via clarification requests and plan approval

The agent has two categories of tools:

**Read-only tools** (always available):
- `list_pods`, `get_pod_logs`, `describe_pod`
- `list_deployments`, `list_namespaces`, `get_resource`
- `http_request`, `wait_for_pod_ready`, `check_service_endpoints`

**Mutating tools** (require user approval):
- `scale_deployment`, `apply_manifest`, `delete_resource`, `exec_in_pod`

### Mission Lifecycle

```
          ┌─────────┐
          │ pending │
          └────┬────┘
               │ worker picks up
               ▼
          ┌─────────┐
     ┌────│ running │────┐
     │    └────┬────┘    │
     │         │         │
     │ clarification  mutation
     │ needed        planned
     │         │         │
     ▼         │         ▼
┌────────────────┐  ┌────────────────┐
│   awaiting_    │  │   awaiting_    │
│ clarification  │  │   approval     │
└───────┬────────┘  └───────┬────────┘
        │                   │
        │ user responds     │ user approves/rejects
        │                   │
        └─────────┬─────────┘
                  │
                  ▼
             ┌─────────┐
             │ running │ (continues execution)
             └────┬────┘
                  │
        ┌─────────┴─────────┐
        │                   │
        ▼                   ▼
   ┌───────────┐      ┌────────┐
   │ completed │      │ failed │
   └───────────┘      └────────┘
```

### Authentication Flow

The UI uses OAuth2 Authorization Code Flow with Keycloak:

1. User visits Mission Control UI (`:30901`)
2. Flask backend redirects to Keycloak for authentication
3. User logs in (demo users: `alice/password`, `bob/password`)
4. Keycloak redirects back with authorization code
5. Backend exchanges code for access token
6. Session established - user can now submit missions

### RBAC Permissions

The agent's ServiceAccount (`devoops-agent`) has:

**Read access to:**
- pods, pods/log, deployments, services, configmaps, secrets
- namespaces, events, endpoints, persistentvolumeclaims

**Write access to:**
- pods, services, configmaps, secrets, persistentvolumeclaims
- deployments, statefulsets, daemonsets, replicasets, ingresses

**Exec access to:**
- pods/exec (for `exec_in_pod` tool)

## Example Missions

The agent can handle missions like:
- "List all pods in the default namespace"
- "Scale the nginx deployment to 3 replicas"
- "Find all pods using more than 500Mi of memory"
- "Check if there are any crashlooping pods and investigate why"
- "Deploy a simple nginx web server with a Service and test it"

## Security Considerations

- The agent has elevated cluster permissions - review `k8s/rbac.yaml`
- Human-in-the-loop approval is required for all mutating operations
- Demo credentials should be changed for any non-local deployment
- Consider network policies to restrict agent's network access

## Project Status

Experimental - exploring agent identity and delegation patterns.
