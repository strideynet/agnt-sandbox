# Shared Keycloak Infrastructure

This directory contains the shared Keycloak identity provider infrastructure used across multiple experiments in the agent sandbox.

## Overview

Keycloak runs as a single shared instance in the `keycloak` namespace. Each experiment creates its own **realm** within this Keycloak instance for isolation.

## Architecture

```
┌─────────────────────────────────────┐
│   Keycloak (keycloak namespace)     │
│                                     │
│  ┌──────────────────────────────┐  │
│  │ Realm: agent-demo            │  │  ← oauth-agent experiment
│  │ - clients, users, etc.       │  │
│  └──────────────────────────────┘  │
│                                     │
│  ┌──────────────────────────────┐  │
│  │ Realm: experiment-2          │  │  ← future experiment
│  │ - clients, users, etc.       │  │
│  └──────────────────────────────┘  │
│                                     │
│  PostgreSQL (shared database)       │
└─────────────────────────────────────┘
```

## Components

- **Keycloak**: Identity and access management server (v26.5.0)
- **PostgreSQL**: Database backend for Keycloak
- **NodePort Service**: External access on port 30080

## Quick Start

### Deploy Shared Infrastructure

```bash
# From repository root
kubectl apply -k shared-infra/keycloak/

# Wait for Keycloak to be ready
kubectl wait -n keycloak --for=condition=ready pod -l app=keycloak --timeout=300s
```

### Access Keycloak

- **Admin Console**: http://localhost:30080/admin
  - Username: `admin`
  - Password: `admin`

- **Internal Service**: `http://keycloak.keycloak.svc.cluster.local:8080`
- **External NodePort**: `http://localhost:30080`

## Realm Setup Pattern

Each experiment should:

1. **Deploy shared Keycloak first** (one-time setup)
2. **Create its own realm** using a setup script in the experiment directory
3. **Use a unique realm name** (convention: `{experiment-name}-realm` or descriptive name)

### Example Realm Setup Script

Experiments should include a `scripts/setup-keycloak.sh` that:

```bash
#!/bin/bash
KEYCLOAK_URL="${KEYCLOAK_URL:-http://localhost:30080}"
REALM="my-experiment-realm"  # Unique per experiment

# Get admin token
# Create realm
# Create clients
# Create users
# etc.
```

See [oauth-agent/scripts/setup-keycloak.sh](../../oauth-agent/scripts/setup-keycloak.sh) for a complete example.

## Configuration

### Default Credentials (Development Only)

- **Keycloak Admin**: admin / admin
- **PostgreSQL**: keycloak / keycloak-dev-password

**⚠️ WARNING**: These are development credentials only. Never use in production.

### Resources

- **Keycloak**: 512Mi-1Gi memory, 500m-1000m CPU
- **PostgreSQL**: 256Mi-512Mi memory, 250m-500m CPU
- **Storage**: 1Gi persistent volume for PostgreSQL

## Features Enabled

- **Token Exchange**: Enabled via `--features=token-exchange` flag
- **Health Endpoints**: `/health/ready`, `/health/live`
- **Metrics**: Enabled for monitoring

## Cleanup

To remove the shared Keycloak infrastructure:

```bash
kubectl delete -k shared-infra/keycloak/
```

**Note**: This will delete ALL realms and data for all experiments using this Keycloak instance.

## Experiments Using This Infrastructure

- [oauth-agent](../../oauth-agent/) - OAuth2 delegation experiment (realm: `agent-demo`)

## Design Notes

### Why Shared?

- **Resource Efficiency**: One Keycloak instance vs. one per experiment
- **Realistic**: Production systems often have a single identity provider
- **Isolation**: Realms provide logical separation between experiments

### Why Separate Realms?

- **Isolation**: Each experiment's users, clients, and configuration are isolated
- **Clean Boundaries**: Easy to understand which resources belong to which experiment
- **Independent Lifecycle**: Can reset/recreate one realm without affecting others

### Alternative Approaches Considered

1. **One Keycloak per experiment**: Too resource-heavy for development
2. **Shared realm**: No isolation, would require careful client naming
3. **External Keycloak**: Loses the self-contained nature of the sandbox
