# Agent Sandbox

An experimental repository for exploring agent architectures, identity, and permission delegation.

## Overview

This repository investigates how agents can operate with their own identity while acting on behalf of users. Rather than traditional agents that run on a user's local machine, these experiments focus on **long-lived agents running in remote environments** (like Kubernetes clusters) with **delegated permissions**.

## Core Questions

- **Identity**: How do agents maintain their own identity separate from users?
- **Delegation**: How do users grant specific permissions to agents?
- **Trust**: What are the security and audit implications of agent authority?
- **Persistence**: How do long-running agents operate across multiple tasks/users?

## Projects

### [devoops/](devoops/)

A Kubernetes DevOps agent that runs inside a cluster with its own ServiceAccount identity. It can:
- Execute natural language missions (e.g., "deploy nginx and verify it works")
- Create and manage Kubernetes resources
- Test its own changes (HTTP requests, pod exec, etc.)
- Operate with RBAC-controlled permissions

**Key Features:**
- Uses Claude API for reasoning and tool execution
- Runs as a long-lived pod with ServiceAccount credentials
- All actions are logged and auditable
- Permission boundaries defined via Kubernetes RBAC

**Status:** Functional prototype demonstrating basic agent capabilities and identity separation

### [oauth-agent/](oauth-agent/)

An experimental agent exploring OAuth2-based user delegation and impersonation. The agent:
- Has its own OAuth2 client identity in Keycloak
- Receives user consent to act on their behalf via standard OAuth2 flows
- Uses delegated access tokens to impersonate users when calling APIs
- Allows users to revoke agent access ("kick" the agent)

**Key Features:**
- Full OAuth2 authorization code flow implementation
- Automatic token refresh for long-lived operation
- Web-based consent interface for users
- Demo API service that validates OAuth2 tokens
- Scripts for easy Keycloak configuration

**Status:** Experimental - exploring consent flows, token management, and permission subscoping

## Future Directions

- **Token Subscoping**: Use OAuth2 token exchange to limit agent permissions per-mission
- Time-limited or mission-scoped permissions
- Multi-user agent scenarios (one agent, multiple delegations)
- Agent-to-agent delegation patterns
- Cross-cluster or multi-environment agents
- Audit logging and action attribution

## Getting Started

Each project directory contains its own README with setup instructions. Start with [devoops/](devoops/) to see a working example.

## Philosophy

This is an **exploration**, not a production system. The goal is to learn about the problem space of agent identity and delegation by building concrete examples and discovering where the interesting challenges lie.
