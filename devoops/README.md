# Devoops - Kubernetes DevOps Agent

A prompt-driven agent that runs inside a Kubernetes cluster and can perform DevOps tasks on behalf of users.

## Overview

Devoops is an experimental agent that explores the concept of long-lived agents with delegated permissions. It runs as a pod in a Kubernetes cluster, uses its own ServiceAccount identity, and can execute DevOps tasks based on natural language mission prompts.

## Architecture

- **Runtime**: Python container running in Kubernetes
- **Identity**: Kubernetes ServiceAccount with RBAC permissions
- **Intelligence**: Claude API with tool calling
- **Scope**: Single cluster (in-cluster operations only)

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

The agent uses Claude's reasoning to break down the mission and execute appropriate Kubernetes operations.

## Quick Start

### Prerequisites

- Python 3.11+
- A Kubernetes cluster
- Anthropic API key

### Local Development

Test the agent locally (it will use your kubeconfig):

```bash
cd devoops
pip install -e .
export ANTHROPIC_API_KEY="your-api-key"
export MISSION="List all pods in the default namespace"
python -m devoops
```

### Deploy to Kubernetes

1. **Build the container image:**

```bash
cd devoops
docker build -t devoops:latest .
```

For local testing with kind/minikube, load the image:
```bash
# For kind:
kind load docker-image devoops:latest

# For minikube:
minikube image load devoops:latest
```

2. **Configure your API key:**

Create `k8s/secret.env` from the example:
```bash
cp k8s/secret.env.example k8s/secret.env
```

Edit `k8s/secret.env` and add your actual Anthropic API key. This file is gitignored and won't be committed.

3. **Set the mission:**

Edit `k8s/deployment.yaml` and update the `MISSION` environment variable with your desired task.

4. **Deploy:**

```bash
kubectl apply -k k8s/
```

5. **Watch the agent work:**

```bash
kubectl logs -n devoops -f deployment/devoops-agent
```

6. **Clean up:**

```bash
kubectl delete -k k8s/
```

## Security Considerations

⚠️ This agent has elevated permissions in your cluster. The RBAC configuration defines what it can and cannot do. Review [k8s/rbac.yaml](k8s/rbac.yaml) carefully before deployment.

## Project Status

Experimental - exploring agent identity and delegation patterns.
