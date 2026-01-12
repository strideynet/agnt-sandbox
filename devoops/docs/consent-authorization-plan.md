# Plan: OAuth2 Token Exchange for User-Consented Agent Authorization

## Problem Statement

The devoops agent currently uses Kubernetes impersonation to act on behalf of users. The agent can impersonate **any** user by simply setting `Impersonate-User: <email>` headers—there's no cryptographic proof that the user consented to this delegation. A customer may not trust an agent with arbitrary impersonation capability.

## Solution Overview

Introduce **OAuth2 Token Exchange (RFC 8693)** so users must explicitly grant consent before the agent can act on their behalf. The agent exchanges the user's access token for a delegated token, which serves as proof of consent. Per-cluster policies determine how this delegation is enforced.

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                         Current Flow                            │
├─────────────────────────────────────────────────────────────────┤
│  User Login → Session(email) → Mission → Impersonate-User:email │
│  Problem: No proof user consented; agent can impersonate anyone │
└─────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────┐
│                         New Flow                                │
├─────────────────────────────────────────────────────────────────┤
│  User Login → Consent UI → Token Exchange → Delegated Token     │
│  Mission → Check delegation exists → Use token for K8s auth     │
│  Benefit: Cryptographic proof of consent; per-cluster policies  │
└─────────────────────────────────────────────────────────────────┘
```

## Implementation Steps

### Step 1: Create `devoops-agent` Keycloak Client for Token Exchange

**File:** `devoops/scripts/setup_realm.py`

Add a new confidential client `devoops-agent` with token exchange enabled:

```python
agent_client_config = {
    "clientId": "devoops-agent",
    "name": "Devoops Agent (Token Exchange)",
    "enabled": True,
    "clientAuthenticatorType": "client-secret",
    "secret": "<agent-secret>",
    "publicClient": False,
    "standardFlowEnabled": False,
    "directAccessGrantsEnabled": False,
    "serviceAccountsEnabled": True,
}
```

Configure token exchange permission: `devoops-ui-client` users can exchange tokens for `devoops-agent` tokens.

### Step 2: Create Delegation Store (In-Memory MVP)

**New file:** `devoops/devoops/delegation_store.py`

```python
@dataclass
class Delegation:
    user_email: str
    user_sub: str           # Keycloak subject ID
    access_token: str       # Delegated token from exchange
    refresh_token: str
    scopes: List[str]       # e.g., ["cluster:local:*", "cluster:prod:read"]
    granted_at: datetime
    token_expires_at: float

class DelegationStore:
    """In-memory delegation store. Delegations lost on restart (MVP)."""
    _delegations: Dict[str, Delegation] = {}

    def store_delegation(user_email, tokens, scopes) -> Delegation
    def get_delegation(user_email) -> Optional[Delegation]
    def revoke_delegation(user_email) -> bool
    def has_valid_delegation(user_email) -> bool
```

Handles token refresh automatically when tokens are near expiry. Users will need to re-consent after agent restart (acceptable for MVP).

### Step 3: Add OAuth Client for Token Exchange

**New file:** `devoops/devoops/oauth_client.py`

```python
class OAuthClient:
    def exchange_token(user_access_token: str) -> Dict[str, Any]:
        """RFC 8693 token exchange: user token → agent-delegated token"""
        data = {
            "grant_type": "urn:ietf:params:oauth:grant-type:token-exchange",
            "subject_token": user_access_token,
            "subject_token_type": "urn:ietf:params:oauth:token-type:access_token",
            "client_id": AGENT_CLIENT_ID,
            "client_secret": AGENT_CLIENT_SECRET,
        }
        return requests.post(TOKEN_ENDPOINT, data=data).json()
```

### Step 4: Extend Cluster Configuration with `requiresConsent`

**File:** `devoops/devoops/cluster_config.py`

Add new auth type and consent requirement field:

```python
class AuthType(str, Enum):
    AMBIENT = "ambient"
    CERTIFICATE = "certificate"
    TOKEN = "token"
    OIDC = "oidc"                      # NEW: Use OIDC token directly with K8s
    DELEGATED_IMPERSONATE = "delegated_impersonate"  # NEW: Impersonate with consent check

@dataclass
class ClusterConfig:
    # ... existing fields ...
    requires_consent: bool = False  # NEW: If true, delegation must exist
```

### Step 5: Update ClusterRegistry to Enforce Consent

**File:** `devoops/devoops/k8s_tools.py`

```python
class ClusterRegistry:
    def __init__(self, clusters, default_cluster, delegation_store):
        self.delegation_store = delegation_store

    def get_client(self, cluster_name, impersonate_user=None) -> K8sClient:
        cluster = self.clusters[cluster_name]

        if cluster.requires_consent and impersonate_user:
            delegation = self.delegation_store.get_delegation(impersonate_user)
            if not delegation or not delegation.is_valid():
                raise ConsentRequiredError(f"User {impersonate_user} has not granted consent")

            # For OIDC clusters, use the delegated token directly
            if cluster.auth.type == AuthType.OIDC:
                return K8sClient(cluster, oidc_token=delegation.access_token)

        # For DELEGATED_IMPERSONATE, continue with impersonation but consent is verified
        return K8sClient(cluster, impersonate_user=impersonate_user)
```

### Step 6: Add Consent UI Components

**New file:** `devoops/ui-react/src/pages/ConsentPage.tsx`

- Shows list of clusters with consent toggle
- Allows per-cluster scope selection (read-only vs read-write)
- Calls `/api/consent/grant` on submit

**File:** `devoops/ui-react/src/api/client.ts`

Add methods:
- `getConsentStatus(): Promise<ConsentStatus>`
- `grantConsent(scopes: string[]): Promise<void>`
- `revokeConsent(): Promise<void>`

### Step 7: Add Consent API Endpoints to UI Backend

**File:** `devoops/ui/app.py`

```python
@app.route("/api/consent/status")
@login_required
def consent_status():
    # Check if user has delegation in agent's store

@app.route("/api/consent/grant", methods=["POST"])
@login_required
def grant_consent():
    # Forward user's access_token to agent for token exchange

@app.route("/api/consent/revoke", methods=["POST"])
@login_required
def revoke_consent():
    # Delete user's delegation from agent's store
```

### Step 8: Add Delegation API Endpoints to Agent

**File:** `devoops/devoops/agent.py`

```python
@app.route("/api/delegations", methods=["POST"])
def create_delegation():
    # Perform token exchange and store delegation

@app.route("/api/delegations/<user_email>", methods=["GET"])
def get_delegation(user_email):
    # Return delegation status

@app.route("/api/delegations/<user_email>", methods=["DELETE"])
def revoke_delegation(user_email):
    # Remove delegation
```

### Step 9: Update Mission Execution to Verify Consent

**File:** `devoops/devoops/agent.py`

In `_execute_mission_internal()`:

```python
def _execute_mission_internal(self, mission: Mission):
    triggered_by = mission.triggered_by

    # Check if any cluster in this mission requires consent
    # (This happens automatically via ClusterRegistry.get_client())

    # If ConsentRequiredError is raised, mission fails with clear message
```

### Step 10: Update Cluster Config Examples

**File:** `devoops/k8s/agent/cluster-config.yaml`

```yaml
clusters:
  - name: "local"
    displayName: "Local Cluster"
    auth:
      type: "delegated_impersonate"  # Use impersonation, but require consent
    requiresConsent: true
    impersonateGroup: "devoops-users"

  - name: "sandbox"
    displayName: "Sandbox (No Consent)"
    auth:
      type: "ambient"
    requiresConsent: false  # Trusted environment
```

## Files to Create

| File | Purpose |
|------|---------|
| `devoops/devoops/delegation_store.py` | Delegation storage with token refresh |
| `devoops/devoops/oauth_client.py` | Token exchange with Keycloak |
| `devoops/devoops/exceptions.py` | `ConsentRequiredError` exception |
| `devoops/ui-react/src/pages/ConsentPage.tsx` | Consent UI |

## Files to Modify

| File | Changes |
|------|---------|
| `devoops/scripts/setup_realm.py` | Add `devoops-agent` client with token exchange |
| `devoops/devoops/cluster_config.py` | Add `OIDC`, `DELEGATED_IMPERSONATE` auth types; add `requires_consent` field |
| `devoops/devoops/k8s_tools.py` | Inject `DelegationStore`; enforce consent in `get_client()` |
| `devoops/devoops/agent.py` | Initialize `DelegationStore`; add delegation API endpoints |
| `devoops/ui/app.py` | Add consent proxy endpoints |
| `devoops/ui-react/src/App.tsx` | Add `/consent` route |
| `devoops/ui-react/src/api/client.ts` | Add consent API methods |
| `devoops/k8s/agent/cluster-config.yaml` | Update with `requiresConsent` examples |

## Migration Path

1. **Phase 1 (Non-breaking):** Add consent infrastructure. Existing clusters continue with `requiresConsent: false`.
2. **Phase 2:** Enable `requiresConsent: true` for sensitive clusters. Users must grant consent.
3. **Phase 3 (Future):** For clusters with OIDC configured, use delegated tokens directly for full K8s-native identity.

## Security Benefits

- **Explicit Consent:** User must actively grant permission via UI
- **Cryptographic Proof:** Delegated token proves user authorized the agent
- **Revocable:** User can revoke consent at any time
- **Per-Cluster Policies:** Different trust levels for different environments
- **Token Refresh:** Automatic token renewal maintains security
- **Audit Trail:** Token exchange creates Keycloak audit log entry

---

## Appendix A: Keycloak Token Exchange Configuration

> Reference: [Keycloak Token Exchange Documentation](https://www.keycloak.org/securing-apps/token-exchange)

### How Keycloak Enforces Consent

Keycloak 26.2+ has full RFC 8693 token exchange support enabled by default. The consent enforcement works as follows:

#### 1. Audience Validation (Built-in)

The `subject_token` (user's original token) **must** have the requesting client (`devoops-agent`) in its `aud` claim. This is configured via an **Audience Mapper** on `devoops-ui-client`:

```
Token issued by devoops-ui-client must include:
{
  "aud": ["devoops-ui-client", "devoops-agent"],  // agent must be in audience
  "azp": "devoops-ui-client",
  "sub": "user-uuid",
  "email": "alice@example.com"
}
```

If the agent is not in the audience, the token exchange request is rejected.

#### 2. Consent Requirement (Optional)

If `devoops-ui-client` has **Consent Required** enabled, the token exchange only succeeds if the user has previously granted consent to all requested scopes. This creates an explicit consent checkpoint.

#### 3. Client Policies (Advanced)

For fine-grained control, Keycloak Client Policies can enforce rules like:
- "Reject exchange if requester requests `scope=admin`"
- "Only allow exchange during business hours"
- "Require specific claims in the subject token"

### Keycloak Setup Script Changes

**File:** `devoops/scripts/setup_realm.py`

```python
# 1. Create the agent client with token exchange enabled
agent_client_config = {
    "clientId": "devoops-agent",
    "name": "Devoops Agent",
    "description": "Agent that acts on behalf of users in Kubernetes",
    "enabled": True,
    "clientAuthenticatorType": "client-secret",
    "secret": os.environ.get("AGENT_CLIENT_SECRET", "devoops-agent-secret-change-me"),
    "protocol": "openid-connect",
    "publicClient": False,
    "standardFlowEnabled": False,        # Agent doesn't do user login
    "directAccessGrantsEnabled": False,
    "serviceAccountsEnabled": True,      # Required for token exchange
    "attributes": {
        "oauth2.token.exchange.grant.enabled": "true",  # Enable token exchange
    },
}

# 2. Add audience mapper to devoops-ui-client so user tokens include devoops-agent
audience_mapper = {
    "name": "devoops-agent-audience",
    "protocol": "openid-connect",
    "protocolMapper": "oidc-audience-mapper",
    "config": {
        "included.client.audience": "devoops-agent",
        "id.token.claim": "true",
        "access.token.claim": "true",
    }
}
# Add to devoops-ui-client's protocol mappers
```

### Token Exchange Request Format

```http
POST /realms/devoops/protocol/openid-connect/token HTTP/1.1
Host: keycloak.example.com
Content-Type: application/x-www-form-urlencoded
Authorization: Basic base64(devoops-agent:secret)

grant_type=urn:ietf:params:oauth:grant-type:token-exchange
&subject_token=<user's access token>
&subject_token_type=urn:ietf:params:oauth:token-type:access_token
&requested_token_type=urn:ietf:params:oauth:token-type:access_token
&audience=devoops-agent
```

### Response Token Structure

The exchanged token will contain:

```json
{
  "iss": "https://keycloak.example.com/realms/devoops",
  "sub": "user-uuid-from-original-token",    // Original user's identity preserved
  "aud": "devoops-agent",                    // Issued FOR the agent
  "azp": "devoops-agent",                    // Authorized party is the agent
  "email": "alice@example.com",              // User claims carried over
  "preferred_username": "alice",
  "act": {                                   // Actor claim (optional)
    "sub": "devoops-agent-service-account"
  },
  "exp": 1234567890,
  "iat": 1234567590
}
```

The `sub` claim still identifies the original user, but `azp` shows the agent performed the exchange. This provides:
- **User identity**: Kubernetes sees the real user
- **Agent attribution**: Audit logs show the agent acted on user's behalf
- **Consent proof**: Token only exists if exchange was allowed

---

## Appendix B: Kubernetes OIDC Authentication Configuration

> Reference: [Kubernetes Authentication Documentation](https://kubernetes.io/docs/reference/access-authn-authz/authentication/)

For clusters using `auth.type: oidc`, the Kubernetes API server must be configured to trust tokens from Keycloak.

### Option 1: Command-Line Flags (Simple)

Add these flags to the kube-apiserver:

```bash
--oidc-issuer-url=https://keycloak.example.com/realms/devoops
--oidc-client-id=devoops-agent
--oidc-username-claim=email
--oidc-groups-claim=groups
--oidc-ca-file=/etc/kubernetes/pki/keycloak-ca.crt
```

| Flag | Value | Purpose |
|------|-------|---------|
| `--oidc-issuer-url` | Keycloak realm URL | Must match `iss` claim in tokens |
| `--oidc-client-id` | `devoops-agent` | Tokens must have this in `aud` claim |
| `--oidc-username-claim` | `email` | K8s username = user's email |
| `--oidc-groups-claim` | `groups` | Map Keycloak groups to K8s groups |
| `--oidc-ca-file` | CA cert path | For TLS verification of Keycloak |

### Option 2: Structured Authentication Config (Kubernetes 1.30+)

For more flexibility, use `--authentication-config`:

```yaml
# /etc/kubernetes/auth-config.yaml
apiVersion: apiserver.config.k8s.io/v1
kind: AuthenticationConfiguration
jwt:
  - issuer:
      url: https://keycloak.example.com/realms/devoops
      audiences:
        - devoops-agent
      audienceMatchPolicy: MatchAny
      certificateAuthority: |
        -----BEGIN CERTIFICATE-----
        <Keycloak CA certificate>
        -----END CERTIFICATE-----
    claimMappings:
      username:
        claim: email
        prefix: ""
      groups:
        claim: groups
        prefix: "oidc:"
      uid:
        claim: sub
    claimValidationRules:
      # Require tokens to be issued for the agent (proves delegation)
      - claim: azp
        requiredValue: devoops-agent
      # Optional: Limit token lifetime
      - expression: 'claims.exp - claims.iat <= 3600'
        message: "Token lifetime must not exceed 1 hour"
```

### Cluster-Specific OIDC Configuration

Different clusters may have different Keycloak realms or trust requirements:

```yaml
# devoops/k8s/agent/cluster-config.yaml
clusters:
  - name: "production"
    displayName: "Production Cluster"
    auth:
      type: "oidc"
      server: "https://k8s-prod.example.com:6443"
      certificateAuthorityData: "base64-encoded-ca"
      # OIDC-specific fields for K8sClient
      oidcIssuer: "https://keycloak.example.com/realms/devoops"
      oidcAudience: "devoops-agent"
    requiresConsent: true

  - name: "staging"
    displayName: "Staging Cluster"
    auth:
      type: "oidc"
      server: "https://k8s-staging.example.com:6443"
      certificateAuthorityData: "base64-encoded-ca"
      oidcIssuer: "https://keycloak.example.com/realms/devoops-staging"
      oidcAudience: "devoops-agent-staging"
    requiresConsent: true
```

### RBAC for OIDC-Authenticated Users

When using OIDC, users are identified by their email (or configured claim). Create RBAC bindings:

```yaml
# k8s/rbac-oidc.yaml
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRoleBinding
metadata:
  name: devoops-oidc-users
roleRef:
  apiGroup: rbac.authorization.k8s.io
  kind: ClusterRole
  name: devoops-users  # Same permissions as impersonation model
subjects:
  # Option 1: Bind specific users by email
  - kind: User
    name: alice@example.com
    apiGroup: rbac.authorization.k8s.io
  - kind: User
    name: bob@example.com
    apiGroup: rbac.authorization.k8s.io

  # Option 2: Bind by Keycloak group (requires groups claim)
  - kind: Group
    name: oidc:devoops-users  # Prefixed with oidc: per config
    apiGroup: rbac.authorization.k8s.io
```

### K8sClient Changes for OIDC Auth

**File:** `devoops/devoops/k8s_tools.py`

```python
class K8sClient:
    def __init__(self, cluster_config, impersonate_user=None, oidc_token=None):
        configuration = client.Configuration()

        if cluster_config.auth.type == AuthType.OIDC:
            # Use OIDC token directly - no impersonation needed
            configuration.host = cluster_config.auth.server
            configuration.ssl_ca_cert = self._write_ca_cert(cluster_config.auth)
            configuration.api_key = {"authorization": f"Bearer {oidc_token}"}
            # No impersonation headers - K8s sees user identity from token

        elif cluster_config.auth.type == AuthType.DELEGATED_IMPERSONATE:
            # Use ambient auth with impersonation (consent already verified)
            config.load_incluster_config(client_configuration=configuration)
            if impersonate_user:
                api_client.set_default_header("Impersonate-User", impersonate_user)
                api_client.set_default_header("Impersonate-Group", cluster_config.impersonate_group)
```

### Kubernetes Audit Log Comparison

**With Impersonation:**
```json
{
  "user": {
    "username": "system:serviceaccount:devoops:devoops-agent",
    "groups": ["system:serviceaccounts"]
  },
  "impersonatedUser": {
    "username": "alice@example.com",
    "groups": ["devoops-users"]
  }
}
```

**With OIDC:**
```json
{
  "user": {
    "username": "alice@example.com",
    "uid": "keycloak-user-uuid",
    "groups": ["oidc:devoops-users"]
  }
}
```

The OIDC approach shows the user as the direct actor, with no impersonation layer.

---

## Appendix C: Docker Desktop Kubernetes OIDC Setup

Since you're using Docker Desktop, here's how to configure OIDC auth for the local cluster:

### 1. Expose Keycloak Externally

Keycloak must be accessible from the K8s API server. With Docker Desktop:

```yaml
# Keycloak service with NodePort
apiVersion: v1
kind: Service
metadata:
  name: keycloak
  namespace: keycloak
spec:
  type: NodePort
  ports:
    - port: 8080
      nodePort: 30080
  selector:
    app: keycloak
```

### 2. Configure Docker Desktop Kubernetes

Docker Desktop doesn't expose kube-apiserver flags directly. Options:

**Option A: Use `delegated_impersonate` for local development**
- Keep using impersonation locally
- OIDC only for production clusters
- Simpler setup, still validates consent

**Option B: Use a proxy/webhook authenticator**
- Deploy an authenticating proxy that validates OIDC tokens
- Routes to the real API server

**Option C: Use kind/k3d instead for OIDC testing**
- These allow full API server configuration
- Better for testing the full OIDC flow

### Recommended Local Setup

```yaml
# cluster-config.yaml for development
clusters:
  - name: "local"
    displayName: "Local (Docker Desktop)"
    auth:
      type: "delegated_impersonate"  # Impersonation with consent check
    requiresConsent: true
    impersonateGroup: "devoops-users"
```

This validates consent locally while allowing full OIDC in production clusters.

---

## Appendix D: Alternative Approach — Direct OIDC (No Token Exchange)

Instead of using token exchange, the Kubernetes clusters could directly trust tokens issued by Keycloak with `aud: devoops-ui-client` (i.e., tokens intended for the UI client). This appendix compares both approaches.

### How Direct OIDC Would Work

```
┌─────────────────────────────────────────────────────────────────┐
│                    Direct OIDC Flow                             │
├─────────────────────────────────────────────────────────────────┤
│  User Login → Access Token (aud: devoops-ui-client)             │
│  Agent stores token → Uses directly with K8s API                │
│  K8s configured with: --oidc-client-id=devoops-ui-client        │
└─────────────────────────────────────────────────────────────────┘
```

#### Implementation

1. **Keycloak**: No changes needed beyond existing `devoops-ui-client`
2. **Agent**: Store user's access token from login session
3. **Kubernetes**: Configure OIDC to accept tokens with `aud: devoops-ui-client`

```yaml
# K8s API server config for direct OIDC
--oidc-issuer-url=https://keycloak.example.com/realms/devoops
--oidc-client-id=devoops-ui-client    # Trust UI client directly
--oidc-username-claim=email
```

#### Agent Code (Simplified)

```python
# No token exchange needed - just pass through the user's token
class DelegationStore:
    def store_user_token(self, user_email: str, access_token: str, refresh_token: str):
        """Store user's original token for later use."""
        self._delegations[user_email] = Delegation(
            user_email=user_email,
            access_token=access_token,  # User's original token
            refresh_token=refresh_token,
            # ...
        )
```

### Comparison: Token Exchange vs Direct OIDC

| Aspect | Token Exchange | Direct OIDC |
|--------|----------------|-------------|
| **Complexity** | Higher - requires agent client, audience mapper, exchange endpoint | Lower - just pass through user tokens |
| **Keycloak Config** | New client + audience mapper | No changes |
| **K8s sees** | `azp: devoops-agent` (agent attribution) | `azp: devoops-ui-client` (UI attribution) |
| **Token scope** | Can be narrowed during exchange | Full user token scope |
| **Consent proof** | Exchange itself proves consent | Consent = user logged in |
| **Audit clarity** | Clear: "agent acted for user" | Ambiguous: "user or agent?" |
| **Token lifetime control** | Agent can request shorter-lived tokens | Bound to UI client settings |
| **Revocation** | Revoke agent tokens independently | Revoking affects UI too |

### Pros of Direct OIDC (No Token Exchange)

1. **Simpler Implementation**
   - No new Keycloak client needed
   - No audience mapper configuration
   - No token exchange endpoint calls
   - Fewer moving parts to debug

2. **Faster Token Acquisition**
   - No extra round-trip to Keycloak for exchange
   - User token is immediately usable

3. **Easier to Understand**
   - "User logs in, agent uses their token" is straightforward
   - Less OAuth2 expertise required to maintain

4. **Works with Any OIDC Provider**
   - Token exchange (RFC 8693) support varies across providers
   - Direct OIDC works with any standard OIDC provider

### Cons of Direct OIDC (No Token Exchange)

1. **Agent Attribution Requires Extra Configuration**
   - The `azp` claim IS in the token, but K8s doesn't expose it by default
   - Must explicitly map `azp` to an "extra" field using structured auth config (K8s 1.30+):
     ```yaml
     claimMappings:
       extra:
         - key: 'devoops.io/authorized-party'
           valueExpression: 'claims.azp'
     ```
   - With this config, audit logs would show:
     ```json
     {
       "user": {
         "username": "alice@example.com",
         "extra": {
           "devoops.io/authorized-party": ["devoops-ui-client"]
         }
       }
     }
     ```
   - **However**: With direct OIDC, `azp` is always `devoops-ui-client` whether the user is in the browser OR using the agent — so it doesn't help distinguish the two paths
   - With token exchange, `azp` would be `devoops-agent`, making it clear the agent was involved

2. **Consent is Implicit**
   - User logging in ≠ consenting to agent delegation
   - No explicit "grant agent access" checkpoint
   - May not satisfy compliance requirements that need explicit consent

3. **Token Scope Cannot Be Narrowed**
   - Agent gets full token with all user's scopes
   - Cannot issue agent-specific reduced-privilege tokens
   - Violates principle of least privilege

4. **Token Lifecycle Coupling**
   - Token expiry tied to UI session settings
   - Cannot have different lifetimes for UI vs agent use
   - Revoking user's UI session also breaks agent

5. **Multi-Tenant Security Concerns**
   - If agent is compromised, attacker has full user tokens
   - With token exchange, attacker only has agent-scoped tokens
   - Exchange tokens can have shorter lifetimes

6. **Less Flexibility for Future Features**
   - Token exchange enables:
     - Per-cluster scoped tokens
     - Time-limited delegations
     - Delegation to specific operations only
   - Direct OIDC is all-or-nothing

### When to Use Each Approach

#### Choose Direct OIDC If:

- You're building an MVP and want simplicity
- Audit log attribution isn't a compliance requirement
- All users who log in implicitly consent to agent usage
- You don't need per-cluster or per-operation scoping
- Your OIDC provider doesn't support token exchange

#### Choose Token Exchange If:

- You need explicit user consent for agent delegation
- Audit logs must distinguish agent actions from direct user actions
- You want to issue reduced-scope tokens to the agent
- Different clusters need different trust levels
- You may need to revoke agent access without affecting user sessions
- Security/compliance requires principle of least privilege

### Hybrid Approach: Direct OIDC with Consent Gate

A middle-ground approach that keeps simplicity but adds explicit consent:

```
┌─────────────────────────────────────────────────────────────────┐
│                    Hybrid Flow                                  │
├─────────────────────────────────────────────────────────────────┤
│  User Login → Access Token → Consent UI ("Allow agent?")        │
│  If consented: Store token in DelegationStore                   │
│  Agent uses user's original token (no exchange)                 │
│  K8s trusts devoops-ui-client                                   │
└─────────────────────────────────────────────────────────────────┘
```

#### Implementation

```python
# Consent endpoint - no token exchange, just record consent
@app.route("/api/consent/grant", methods=["POST"])
@login_required
def grant_consent():
    user_email = session.get("email")
    access_token = session.get("access_token")
    refresh_token = session.get("refresh_token")

    # Store user's original token (no exchange)
    response = requests.post(
        f"{AGENT_URL}/api/delegations",
        json={
            "user_email": user_email,
            "access_token": access_token,      # User's original token
            "refresh_token": refresh_token,
            "scopes": data.get("scopes", ["*"]),
        },
    )
    return response.json(), response.status_code
```

#### Pros of Hybrid

- Explicit consent checkpoint (user clicks "Grant Access")
- No token exchange complexity
- Agent still validates consent before using token
- Simpler Keycloak configuration

#### Cons of Hybrid

- No agent attribution in K8s audit logs
- Still uses full-scope user tokens
- Consent is application-level, not OAuth2-level

### Recommendation

For the devoops agent, **token exchange is recommended** because:

1. **Customer Trust**: Customers who don't trust arbitrary impersonation likely also want to see clear agent attribution in audit logs

2. **Explicit Consent**: OAuth2 token exchange is the standard way to delegate authority — it's auditable in Keycloak

3. **Future-Proofing**: Token exchange enables per-cluster scoping, which aligns with your per-cluster policy requirement

4. **Security Posture**: Reduced-scope agent tokens limit blast radius if agent is compromised

However, if you want to **start simpler**, the hybrid approach (direct OIDC + consent gate) is a reasonable stepping stone that can be upgraded to token exchange later.
