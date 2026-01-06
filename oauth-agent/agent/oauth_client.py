"""
OAuth2 Client for Agent

Manages OAuth2 tokens for delegated user access.
"""

import logging
import time
from typing import Optional, Dict, Any
import requests

logger = logging.getLogger(__name__)


class OAuth2Client:
    """Manages OAuth2 tokens and refresh logic."""

    def __init__(
        self,
        token_endpoint: str,
        client_id: str,
        client_secret: str,
        consent_ui_url: str,
        exchange_client_id: str,
        exchange_client_secret: str,
        audience: str = "demo-service"
    ):
        """
        Initialize OAuth2 client.

        Args:
            token_endpoint: Keycloak token endpoint URL
            client_id: OAuth2 client ID (for consent UI)
            client_secret: OAuth2 client secret (for consent UI)
            consent_ui_url: URL of consent UI to fetch user tokens
            exchange_client_id: Agent client ID for token exchange
            exchange_client_secret: Agent client secret for token exchange
            audience: Target audience for exchanged tokens
        """
        self.token_endpoint = token_endpoint
        self.client_id = client_id
        self.client_secret = client_secret
        self.consent_ui_url = consent_ui_url
        self.exchange_client_id = exchange_client_id
        self.exchange_client_secret = exchange_client_secret
        self.audience = audience

        # Token cache: {username: {access_token, refresh_token, expires_at}}
        self._token_cache: Dict[str, Dict[str, Any]] = {}

    def get_user_token(self, username: str) -> Optional[str]:
        """
        Get a valid access token for the specified user.

        This method:
        1. Checks if we have a cached token
        2. If expired, refreshes it
        3. If no token exists, fetches from consent UI

        Args:
            username: The user to get a token for

        Returns:
            Access token string, or None if not available
        """
        # Check cache
        if username in self._token_cache:
            token_info = self._token_cache[username]
            expires_at = token_info.get("expires_at", 0)

            # If token is still valid (with 60s buffer), return it
            if time.time() < expires_at - 60:
                logger.debug(f"Using cached token for {username}")
                return token_info["access_token"]

            # Try to refresh
            logger.info(f"Token for {username} expired, attempting refresh...")
            if self._refresh_token(username):
                return self._token_cache[username]["access_token"]

        # Fetch from consent UI
        logger.info(f"Fetching token for {username} from consent UI...")
        if self._fetch_token_from_ui(username):
            return self._token_cache[username]["access_token"]

        logger.warning(f"No valid token available for {username}")
        return None

    def _fetch_token_from_ui(self, username: str) -> bool:
        """
        Fetch user token from the consent UI and exchange it.

        The consent UI exposes an API endpoint that returns tokens for users
        who have completed the OAuth2 flow. We then exchange this token to
        get an agent-attributed token.

        Args:
            username: The user to fetch token for

        Returns:
            True if successful, False otherwise
        """
        try:
            url = f"{self.consent_ui_url}/api/token/{username}"
            response = requests.get(url, timeout=10)

            if response.status_code == 404:
                logger.warning(f"No delegation found for user {username}")
                return False

            response.raise_for_status()
            token_data = response.json()

            # Exchange the user token for an agent-attributed token
            logger.info(f"Exchanging user token for {username}...")
            exchanged_token = self._exchange_token(token_data["access_token"])

            if not exchanged_token:
                logger.error(f"Failed to exchange token for {username}")
                return False

            # Store exchanged token in cache
            self._token_cache[username] = {
                "access_token": exchanged_token["access_token"],
                "refresh_token": token_data.get("refresh_token"),
                "expires_at": time.time() + exchanged_token.get("expires_in", 300)
            }

            logger.info(f"Successfully fetched and exchanged token for {username}")
            return True

        except Exception as e:
            logger.error(f"Failed to fetch token from UI: {e}")
            return False

    def _refresh_token(self, username: str) -> bool:
        """
        Refresh an expired access token using the refresh token and exchange it.

        Args:
            username: The user whose token to refresh

        Returns:
            True if successful, False otherwise
        """
        if username not in self._token_cache:
            return False

        refresh_token = self._token_cache[username].get("refresh_token")
        if not refresh_token:
            logger.warning(f"No refresh token available for {username}")
            return False

        try:
            data = {
                "grant_type": "refresh_token",
                "refresh_token": refresh_token,
                "client_id": self.client_id,
                "client_secret": self.client_secret
            }

            response = requests.post(self.token_endpoint, data=data, timeout=10)
            response.raise_for_status()
            token_data = response.json()

            # Exchange the refreshed token
            logger.info(f"Exchanging refreshed token for {username}...")
            exchanged_token = self._exchange_token(token_data["access_token"])

            if not exchanged_token:
                logger.error(f"Failed to exchange refreshed token for {username}")
                del self._token_cache[username]
                return False

            # Update cache with exchanged token
            self._token_cache[username] = {
                "access_token": exchanged_token["access_token"],
                "refresh_token": token_data.get("refresh_token", refresh_token),
                "expires_at": time.time() + exchanged_token.get("expires_in", 300)
            }

            logger.info(f"Successfully refreshed and exchanged token for {username}")
            return True

        except Exception as e:
            logger.error(f"Failed to refresh token: {e}")
            # Remove from cache since it's no longer valid
            del self._token_cache[username]
            return False

    def _exchange_token(self, subject_token: str) -> Optional[Dict[str, Any]]:
        """
        Exchange a user token for an agent-attributed token using RFC 8693.

        This implements OAuth2 Token Exchange to get a new token that indicates
        both the user identity (sub) and agent identity (act claim).

        Args:
            subject_token: The user's access token to exchange

        Returns:
            Token data dict with access_token and expires_in, or None if failed
        """
        try:
            data = {
                "grant_type": "urn:ietf:params:oauth:grant-type:token-exchange",
                "subject_token": subject_token,
                "subject_token_type": "urn:ietf:params:oauth:token-type:access_token",
                "requested_token_type": "urn:ietf:params:oauth:token-type:access_token",
                "client_id": self.exchange_client_id,
                "client_secret": self.exchange_client_secret
                # Note: audience parameter not needed when exchanger is in token audience
            }

            response = requests.post(self.token_endpoint, data=data, timeout=10)
            response.raise_for_status()

            token_data = response.json()
            logger.debug(f"Token exchange successful, expires_in: {token_data.get('expires_in')}")

            return token_data

        except Exception as e:
            logger.error(f"Token exchange failed: {e}")
            if hasattr(e, 'response') and e.response is not None:
                logger.error(f"Response: {e.response.text}")
            return None

    def has_delegation(self, username: str) -> bool:
        """
        Check if the agent has a valid delegation for the user.

        Args:
            username: The user to check

        Returns:
            True if we can get a valid token, False otherwise
        """
        token = self.get_user_token(username)
        return token is not None

    def revoke_token(self, username: str) -> bool:
        """
        Revoke tokens for a user (remove from cache).

        In a production system, this should also call the token revocation endpoint.

        Args:
            username: The user whose tokens to revoke

        Returns:
            True if tokens were revoked, False if none existed
        """
        if username in self._token_cache:
            del self._token_cache[username]
            logger.info(f"Revoked cached tokens for {username}")
            return True
        return False
