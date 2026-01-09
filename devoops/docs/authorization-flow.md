# Authorization Flow

This document describes how authorization works in the devoops agent system, highlighting the trust relationships and responsibilities.

## Sequence Diagram

```mermaid
sequenceDiagram
    participant User
    participant Browser
    participant Keycloak as Keycloak (IdP)
    participant UI as UI Backend (Flask)
    participant Agent as Agent Harness
    participant K8s as Kubernetes API

    Note over User,K8s: Authentication Phase
    User->>Browser: Navigate to /login-page
    Browser->>UI: GET /login
    UI->>Browser: Redirect to Keycloak
    Browser->>Keycloak: OAuth2 Authorization Request
    User->>Keycloak: Enter credentials
    Keycloak->>Browser: Redirect with auth code
    Browser->>UI: GET /callback?code=...
    UI->>Keycloak: Exchange code for tokens
    Keycloak->>UI: Access token + ID token
    UI->>UI: Store email in session
    UI->>Browser: Set session cookie

    Note over User,K8s: Mission Submission
    User->>Browser: Submit mission prompt
    Browser->>UI: POST /api/missions {prompt}
    UI->>UI: Extract email from session
    UI->>Agent: POST /api/missions {prompt, triggered_by: email}

    Note over Agent,K8s: Agent Authorization (No User Consent)
    rect rgb(255, 230, 230)
        Note right of Agent: Agent decides to impersonate<br/>user based on triggered_by field.<br/>User never explicitly consented<br/>to this impersonation.
        Agent->>Agent: Create K8sClient with<br/>Impersonate-User: user@email.com<br/>Impersonate-Group: devoops-users
    end

    Note over Agent,K8s: K8s API Calls
    Agent->>K8s: API Request<br/>+ Impersonate-User header<br/>+ Impersonate-Group header
    K8s->>K8s: Verify ServiceAccount can impersonate
    K8s->>K8s: Check devoops-users group RBAC
    K8s->>K8s: Log action as impersonated user
    K8s->>Agent: Response
    Agent->>UI: Mission result
    UI->>Browser: Display result
```

## Key Security Considerations

### Trust Relationships

1. **UI Backend trusts Keycloak** - Session email comes from validated OAuth2 tokens
2. **Agent trusts UI Backend** - The `triggered_by` field is accepted without verification
3. **K8s trusts Agent ServiceAccount** - Impersonation is allowed based on RBAC

### Agent Harness Responsibilities

The agent harness bears significant responsibility:

- **Correct impersonation**: Must accurately pass the user's identity to K8s
- **No privilege escalation**: Can only impersonate the `devoops-users` group (enforced by RBAC `resourceNames`)
- **Audit integrity**: The audit trail depends entirely on the agent sending correct headers

### No Explicit User Consent

Users authenticate with Keycloak but never explicitly authorize the agent to:
- Act on their behalf in Kubernetes
- Use their identity for impersonation
- Perform operations under their name

This is an implicit trust model where using the devoops UI implies consent for the agent to act as you.

### RBAC Constraints

```yaml
# Agent can impersonate any user (for audit)
- resources: [users]
  verbs: [impersonate]

# Agent can ONLY impersonate devoops-users group (limits permissions)
- resources: [groups]
  resourceNames: [devoops-users]
  verbs: [impersonate]
```

The `resourceNames` constraint is critical - it prevents the agent from impersonating privileged groups like `system:masters`.

## Potential Threat Vectors

1. **Compromised Agent**: Could impersonate any user with `devoops-users` permissions
2. **UI Backend Vulnerability**: Could allow injection of arbitrary `triggered_by` values
3. **Session Hijacking**: Attacker could submit missions as another user
4. **Audit Log Manipulation**: Agent controls what identity appears in K8s audit logs
