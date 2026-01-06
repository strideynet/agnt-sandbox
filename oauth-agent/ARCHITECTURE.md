# Architecture - OAuth Agent

Deep dive into the OAuth2 delegation architecture.

## System Components

### 1. Keycloak (Identity Provider)

**Purpose**: OAuth2/OIDC authorization server and identity provider

**Responsibilities**:
- User authentication
- OAuth2 authorization code flow
- Token issuance (access tokens, refresh tokens)
- Token validation (via public keys)
- Session management

**Configuration**:
- Realm: `agent-demo`
- Client: `oauth-agent` (confidential client)
- Users: `alice`, `bob` (demo users)

**Endpoints**:
- Authorization: `/realms/agent-demo/protocol/openid-connect/auth`
- Token: `/realms/agent-demo/protocol/openid-connect/token`
- UserInfo: `/realms/agent-demo/protocol/openid-connect/userinfo`
- Public Keys: `/realms/agent-demo/protocol/openid-connect/certs`

### 2. Consent UI (OAuth2 Client)

**Purpose**: Web interface for user consent and token management

**Responsibilities**:
- Initiate OAuth2 authorization code flow
- Handle authorization callbacks
- Store user tokens (access + refresh)
- Provide token API for agent
- Allow users to revoke access

**Key Files**:
- [ui/app.py](ui/app.py) - Flask application with OAuth2 flow

**Endpoints**:
- `GET /` - Home page (delegation status)
- `GET /authorize` - Start OAuth2 flow
- `GET /callback` - OAuth2 callback handler
- `GET /revoke` - Revoke user delegation
- `GET /api/token/<username>` - Token API for agent

**Security Note**: In production, the `/api/token/<username>` endpoint should require authentication. Currently, it's open for simplicity.

### 3. Demo Service (Resource Server)

**Purpose**: Example API that validates OAuth2 tokens

**Responsibilities**:
- Validate OAuth2 access tokens from Keycloak
- Decode JWT tokens and extract user information
- Provide user-specific APIs
- Demonstrate impersonation

**Key Files**:
- [demo-service/app.py](demo-service/app.py) - Flask API with token validation

**Endpoints**:
- `GET /api/whoami` - Get current user info
- `GET /api/tasks` - List user's tasks
- `POST /api/tasks` - Create a new task
- `POST /api/protected-action` - Perform protected action

**Token Validation**:
1. Extract Bearer token from Authorization header
2. Fetch Keycloak's public keys
3. Verify JWT signature using public key
4. Validate issuer, audience, and expiration
5. Extract user claims (username, email, etc.)

### 4. Agent (OAuth2 Client)

**Purpose**: Long-lived agent that acts with delegated user permissions

**Responsibilities**:
- Fetch user tokens from Consent UI
- Refresh expired tokens automatically
- Execute missions using Claude API
- Call APIs with delegated tokens
- Handle token expiration and revocation

**Key Files**:
- [agent/agent.py](agent/agent.py) - Main agent logic with Claude
- [agent/oauth_client.py](agent/oauth_client.py) - OAuth2 token management
- [agent/tools.py](agent/tools.py) - Tools for interacting with APIs

**Token Management**:
- Caches tokens in memory
- Refreshes tokens 60 seconds before expiration
- Falls back to fetching from Consent UI if needed
- Gracefully handles revocation

## OAuth2 Flow

### Authorization Code Flow (User Consent)

```
┌──────┐                                           ┌─────────┐
│ User │                                           │Keycloak │
└───┬──┘                                           └────┬────┘
    │                                                   │
    │  1. Click "Grant Agent Access"                   │
    ├─────────────────────────────────►┌──────────┐   │
    │                                   │Consent UI│   │
    │                                   └────┬─────┘   │
    │  2. Redirect to authorization          │         │
    │     endpoint with client_id, etc.      │         │
    │  ◄─────────────────────────────────────┤         │
    │                                         │         │
    │  3. GET /auth?client_id=...&redirect_uri=...     │
    ├──────────────────────────────────────────────────►
    │                                                   │
    │  4. Login page (if not authenticated)            │
    │  ◄──────────────────────────────────────────────┤
    │                                                   │
    │  5. User enters credentials                      │
    ├──────────────────────────────────────────────────►
    │                                                   │
    │  6. Consent screen (grant permissions)           │
    │  ◄──────────────────────────────────────────────┤
    │                                                   │
    │  7. User approves                                │
    ├──────────────────────────────────────────────────►
    │                                                   │
    │  8. Redirect to callback with code               │
    │  ◄──────────────────────────────────────────────┤
    │                                                   │
    │  9. GET /callback?code=abc&state=xyz             │
    ├─────────────────────────────────►┌──────────┐   │
    │                                   │Consent UI│   │
    │                                   └────┬─────┘   │
    │                                        │         │
    │                          10. POST /token         │
    │                          (exchange code for      │
    │                           tokens)                │
    │                          ├─────────────────────► │
    │                                        │         │
    │                          11. Return tokens       │
    │                          ◄─────────────────────┤ │
    │                          {                       │
    │                            access_token,         │
    │                            refresh_token,        │
    │                            expires_in            │
    │                          }                       │
    │                                        │         │
    │                          12. Store tokens        │
    │                          13. GET /userinfo       │
    │                          ├─────────────────────► │
    │                                        │         │
    │  14. Success page                      │         │
    │  ◄─────────────────────────────────────┤         │
    │                                                   │
```

### Agent Using Delegated Token

```
┌───────┐                ┌──────────┐              ┌───────────┐
│ Agent │                │Consent UI│              │Demo Service│
└───┬───┘                └────┬─────┘              └─────┬─────┘
    │                         │                          │
    │  1. GET /api/token/alice│                          │
    ├─────────────────────────►                          │
    │                         │                          │
    │  2. Return tokens       │                          │
    │  ◄──────────────────────┤                          │
    │  {access_token, ...}    │                          │
    │                         │                          │
    │  3. GET /api/whoami                                │
    │     Authorization: Bearer <alice's token>          │
    ├────────────────────────────────────────────────────►
    │                                                     │
    │  4. Validate token, extract user info              │
    │                                                     │
    │  5. Return user data                               │
    │  ◄────────────────────────────────────────────────┤
    │  {username: "alice", ...}                          │
    │                                                     │
```

### Token Refresh Flow

```
┌───────┐                ┌─────────┐
│ Agent │                │Keycloak │
└───┬───┘                └────┬────┘
    │                         │
    │  Token expired or       │
    │  about to expire        │
    │                         │
    │  1. POST /token         │
    │     grant_type=refresh_token
    │     refresh_token=...   │
    │     client_id=...       │
    │     client_secret=...   │
    ├─────────────────────────►
    │                         │
    │  2. Validate refresh    │
    │     token and client    │
    │                         │
    │  3. Return new tokens   │
    │  ◄──────────────────────┤
    │  {                      │
    │    access_token,        │
    │    refresh_token (new), │
    │    expires_in           │
    │  }                      │
    │                         │
```

## Token Structure

### Access Token (JWT)

```json
{
  "header": {
    "alg": "RS256",
    "typ": "JWT",
    "kid": "key-id"
  },
  "payload": {
    "iss": "http://keycloak:8080/realms/agent-demo",
    "sub": "user-uuid",
    "aud": "account",
    "exp": 1704153600,
    "iat": 1704150000,
    "preferred_username": "alice",
    "email": "alice@example.com",
    "name": "Alice Demo",
    "scope": "openid profile email"
  },
  "signature": "..."
}
```

### Refresh Token

Opaque string used to obtain new access tokens. Not parsed by the agent, just stored and used when needed.

## Security Considerations

### Token Storage

**Current (Development)**:
- Tokens stored in-memory in Consent UI
- Lost on pod restart
- No encryption

**Production Requirements**:
- Store tokens in encrypted database
- Encrypt tokens at rest
- Rotate encryption keys
- Implement token cleanup on expiration

### Client Secret

**Current**:
- Stored in Kubernetes Secret
- Shared between Consent UI and Agent
- Default value for development

**Production Requirements**:
- Use secrets management system (Vault, AWS Secrets Manager)
- Rotate secrets regularly
- Different secrets per environment
- Monitor secret access

### API Security

**Current Issues**:
- `/api/token/<username>` endpoint is unauthenticated
- Agent can fetch any user's tokens
- No rate limiting

**Production Requirements**:
- Authenticate agent requests (mutual TLS, API keys)
- Implement proper authorization
- Rate limiting and abuse detection
- Audit logging

### Token Scopes

**Current**:
- Agent requests: `openid profile email offline_access`
- Full user impersonation

**Future (Subscoping)**:
- Per-mission scopes
- OAuth2 token exchange for reduced scopes
- Time-limited tokens
- Action-specific permissions

## Deployment Architecture

```
┌─────────────────────────────────────────────────────┐
│                  Kubernetes Cluster                  │
│                                                       │
│  ┌───────────────────────────────────────────────┐  │
│  │          Namespace: oauth-agent                │  │
│  │                                                 │  │
│  │  ┌──────────┐    ┌─────────┐                  │  │
│  │  │PostgreSQL│◄───┤Keycloak │                  │  │
│  │  │  (PVC)   │    │  Pod    │                  │  │
│  │  └──────────┘    └────┬────┘                  │  │
│  │                       │                        │  │
│  │                NodePort:30080                  │  │
│  │                       │                        │  │
│  │  ┌────────────────────┴──────────────────┐    │  │
│  │  │                                        │    │  │
│  │  ▼                                        ▼    │  │
│  │  ┌──────────┐    ┌────────────┐  ┌──────────┐│  │
│  │  │Consent UI│    │ Demo       │  │  Agent   ││  │
│  │  │   Pod    │    │ Service    │  │   Pod    ││  │
│  │  └──────────┘    │   Pod      │  └──────────┘│  │
│  │       │          └────────────┘        │     │  │
│  │ NodePort:30800    NodePort:30500      │     │  │
│  │       │                  │             │     │  │
│  └───────┼──────────────────┼─────────────┼─────┘  │
│          │                  │             │         │
└──────────┼──────────────────┼─────────────┼─────────┘
           │                  │             │
           ▼                  ▼             ▼
    ┌───────────┐      ┌──────────┐  ┌──────────┐
    │  User     │      │  User    │  │  User    │
    │  Browser  │      │  Testing │  │  Logs    │
    └───────────┘      └──────────┘  └──────────┘
```

## Extension Points

### 1. Token Subscoping

Use OAuth2 Token Exchange (RFC 8693) to create limited-scope tokens:

```python
# Exchange user's full token for mission-specific token
def get_subscoped_token(access_token, mission_scope):
    data = {
        "grant_type": "urn:ietf:params:oauth:grant-type:token-exchange",
        "subject_token": access_token,
        "subject_token_type": "urn:ietf:params:oauth:token-type:access_token",
        "requested_token_type": "urn:ietf:params:oauth:token-type:access_token",
        "scope": mission_scope  # e.g., "read:tasks create:tasks"
    }
    # POST to token endpoint...
```

### 2. Audit Logging

Track all agent actions:

```python
def audit_log(username, action, resource, result):
    log_entry = {
        "timestamp": datetime.utcnow(),
        "agent_id": "oauth-agent",
        "user": username,
        "action": action,
        "resource": resource,
        "result": result,
        "mission_id": current_mission_id
    }
    # Store in database, send to logging service, etc.
```

### 3. Time-Limited Delegations

Automatically revoke after a period:

```python
def create_delegation(username, duration_hours):
    expiry = time.time() + (duration_hours * 3600)
    delegation = {
        "username": username,
        "expires_at": expiry,
        "tokens": {...}
    }
    # Schedule revocation job
```

### 4. Per-Mission Permissions

Request different scopes per mission:

```python
def execute_mission(mission, username):
    required_scopes = infer_scopes(mission)
    # Check if current token has required scopes
    # If not, initiate new consent flow with specific scopes
```

## Troubleshooting

### Common Issues

1. **Token validation fails**: Check that token issuer matches Keycloak realm URL
2. **Refresh fails**: Refresh token may have expired (check `ssoSessionMaxLifespan`)
3. **Agent can't get token**: User may not have completed OAuth flow yet
4. **Callback fails**: Check redirect URI matches exactly (including port)

### Debug Commands

```bash
# Check if user has delegation
curl http://localhost:30800/api/token/alice

# Manually validate a token
curl http://localhost:30500/api/whoami \
  -H "Authorization: Bearer <token>"

# View agent logs
kubectl logs -n oauth-agent -l app=oauth-agent -f

# Check Keycloak realm settings
kubectl port-forward -n oauth-agent svc/keycloak 8080:8080
# Visit http://localhost:8080/admin
```
