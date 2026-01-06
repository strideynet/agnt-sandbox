# Keycloak Research Experiments

This directory contains Python scripts that demonstrate core Keycloak OAuth2 and token exchange functionality.

## Overview

These experiments explore two key identity and delegation patterns:

1. **OAuth2 Authorization Code Flow**: How users grant consent to applications
2. **Standard Token Exchange (RFC 8693)**: How services exchange tokens to act on behalf of users

## Prerequisites

- Keycloak deployed and running at `http://localhost:30080`
- Python 3.9+
- [UV](https://github.com/astral-sh/uv) (Python package manager)

## Quick Start

### 1. Setup the Research Realm

First, create the `research` realm with required clients and users:

```bash
cd shared-infra/keycloak/research
uv run python setup_realm.py
```

This creates:
- **Realm**: `research`
- **Clients**:
  - `user-client` (for OAuth2 authorization code flow)
  - `service-client` (for token exchange)
- **Users**: `alice/password`, `bob/password`

### 2. Run User Consent Flow Demo

Demonstrates the OAuth2 authorization code flow with PKCE:

```bash
uv run python user_consent_flow.py
```

**What happens:**
1. Opens browser for user authentication
2. User logs in as alice or bob
3. User grants consent to the application
4. Application receives authorization code
5. Application exchanges code for access & refresh tokens
6. Application uses tokens to access protected resources
7. Application demonstrates token refresh

**Expected Output:**
- Authorization URL and callback server logs
- Decoded access token showing user claims
- Refresh token usage
- User info retrieval from protected endpoint

### 3. Run Token Exchange Demo

Demonstrates Standard Token Exchange (RFC 8693):

```bash
uv run python token_exchange.py
```

**What happens:**
1. Obtains user token via direct grant (simulating a user-authenticated token)
2. Service client exchanges user's token for a new token
3. Shows before/after comparison of tokens
4. Validates exchanged token works with protected resources

**Expected Output:**
- Original token issued to `user-client`
- Exchanged token issued to `service-client` but representing the same user
- Side-by-side comparison showing changes in audience, authorized party, etc.
- Demonstration that service can act on behalf of user

## Scripts

### `setup_realm.py`

Programmatically configures Keycloak using the Admin REST API.

**Purpose**: Document the exact configuration needed for the experiments, making them reproducible.

**Key Configuration:**
- Realm settings (token lifespans, session timeouts)
- Client configurations (secrets, redirect URIs, grants)
- Token exchange enablement
- Demo user creation

**Idempotent**: Safe to run multiple times (updates existing resources).

### `user_consent_flow.py`

Interactive demonstration of OAuth2 authorization code flow.

**Key Concepts:**
- Authorization code flow with PKCE (Proof Key for Code Exchange)
- User authentication and consent
- Code exchange for tokens
- Token refresh mechanism
- Using access tokens to call protected APIs

**Browser Required**: Opens browser for user authentication.

### `token_exchange.py`

Demonstrates RFC 8693 token exchange.

**Key Concepts:**
- Standard Token Exchange grant type
- Audience-based token exchange
- Permission delegation from user to service
- Token claim preservation and modification

**No Browser Required**: Uses direct grant for simplicity.

## Configuration

All scripts use these default values (can be modified at the top of each script):

```python
KEYCLOAK_URL = "http://localhost:30080"
REALM = "research"
```

### Client Credentials

**user-client:**
- Client ID: `user-client`
- Client Secret: `user-client-secret`
- Type: Confidential
- Flows: Authorization Code, Direct Grant

**service-client:**
- Client ID: `service-client`
- Client Secret: `service-client-secret`
- Type: Confidential
- Flows: Service Account, Token Exchange

### Demo Users

- **alice** / password
- **bob** / password

## Understanding Token Exchange

Token exchange allows a service to obtain a token that represents it acting on behalf of a user. This is useful for:

### Use Cases

1. **Backend Services**: Service A needs to call Service B with user context
2. **Audience-Specific Tokens**: Different APIs require tokens with different audiences
3. **Permission Delegation**: User grants service specific capabilities
4. **Microservices**: Pass user context through service chains

### How It Works

```
┌──────────────────────────────────────────────────────────┐
│  User authenticates and gets token from user-client     │
│  Token: {sub: "alice", azp: "user-client"}              │
└──────────────────────────────────────────────────────────┘
                           │
                           ▼
┌──────────────────────────────────────────────────────────┐
│  Service exchanges token using service-client            │
│  Request: grant_type=token-exchange                      │
│           subject_token=<user's token>                   │
│           client_id=service-client                       │
└──────────────────────────────────────────────────────────┘
                           │
                           ▼
┌──────────────────────────────────────────────────────────┐
│  Keycloak issues new token:                              │
│  Token: {sub: "alice", azp: "service-client"}            │
│  Same user, different authorized party                   │
└──────────────────────────────────────────────────────────┘
```

### Key Properties

- **Subject Preserved**: User identity (sub) remains the same
- **Authorized Party Changed**: New token issued to service (azp)
- **Audience Filtered**: Can request specific audience
- **Fresh Expiration**: New token has its own expiration
- **No New Session**: Does not create a new user session

## Keycloak Admin Console

Access the admin console to inspect the configuration:

**URL**: http://localhost:30080/admin

**Credentials**: admin / admin

**Useful Views:**
- Realm Settings → Tokens (see token lifespans)
- Clients → user-client → Settings (see OAuth2 configuration)
- Clients → service-client → Settings (see token exchange enabled)
- Users → alice → Sessions (see active sessions)
- Users → alice → Consent (see granted permissions)

## Troubleshooting

### "Failed to obtain admin token"
- Ensure Keycloak is running: `kubectl get pods -n keycloak`
- Check URL is correct: `http://localhost:30080`

### "Error exchanging token"
- Verify `service-client` has token exchange enabled
- Check `setup_realm.py` ran successfully
- Ensure subject token is valid and not expired

### "Authorization callback failed"
- Check port 8080 is available
- Ensure redirect URI matches in client configuration
- Verify realm name is correct

### Browser doesn't open
- Manually copy the authorization URL from terminal
- Paste into browser to complete flow

## Dependencies

Managed automatically by UV:

- **requests**: HTTP client for Keycloak API calls
- **pyjwt**: JWT token decoding and inspection
- **cryptography**: JWT signature verification support

## Clean Up

To remove the research realm:

1. Open Keycloak admin console
2. Navigate to realm dropdown (top left)
3. Hover over "research" realm
4. Click trash icon

Or delete via API in setup_realm.py (add delete function).

## Further Reading

- [RFC 8693: OAuth 2.0 Token Exchange](https://datatracker.ietf.org/doc/html/rfc8693)
- [Keycloak Token Exchange Documentation](https://www.keycloak.org/securing-apps/token-exchange)
- [OAuth 2.0 Authorization Code Flow](https://oauth.net/2/grant-types/authorization-code/)
- [PKCE: Proof Key for Code Exchange](https://oauth.net/2/pkce/)

## Next Steps

After running these experiments, you can:

1. Modify token lifespans in realm configuration
2. Add custom claims to tokens via client mappers
3. Experiment with different audiences
4. Add additional clients for multi-service scenarios
5. Implement permission-based token downscoping
6. Explore refresh token rotation
