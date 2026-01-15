"""OIDC authentication service."""
import secrets
from dataclasses import dataclass
from urllib.parse import urlencode

import httpx

from app.config import settings


@dataclass
class OIDCUserInfo:
    """User information from OIDC provider."""
    email: str
    name: str | None
    groups: list[str]


class OIDCError(Exception):
    """OIDC authentication error."""
    pass


class OIDCService:
    """Handles OIDC authentication flow."""

    def __init__(self):
        self._discovery_cache: dict | None = None

    async def get_discovery_document(self) -> dict:
        """Fetch and cache the OIDC discovery document."""
        if self._discovery_cache:
            return self._discovery_cache

        if not settings.oidc_issuer_url:
            raise OIDCError("OIDC issuer URL not configured")

        discovery_url = f"{settings.oidc_issuer_url.rstrip('/')}/.well-known/openid-configuration"

        async with httpx.AsyncClient() as client:
            response = await client.get(discovery_url, timeout=10.0)
            if response.status_code != 200:
                raise OIDCError(f"Failed to fetch OIDC discovery document: {response.status_code}")
            self._discovery_cache = response.json()

        return self._discovery_cache

    def generate_state(self) -> str:
        """Generate a random state parameter for CSRF protection."""
        return secrets.token_urlsafe(32)

    async def get_authorization_url(self, state: str) -> str:
        """Build the authorization URL to redirect the user to."""
        discovery = await self.get_discovery_document()
        auth_endpoint = discovery.get("authorization_endpoint")

        if not auth_endpoint:
            raise OIDCError("Authorization endpoint not found in discovery document")

        params = {
            "client_id": settings.oidc_client_id,
            "redirect_uri": settings.get_oidc_redirect_uri(),
            "response_type": "code",
            "scope": "openid email profile groups",
            "state": state,
        }

        return f"{auth_endpoint}?{urlencode(params)}"

    async def exchange_code(self, code: str) -> dict:
        """Exchange authorization code for tokens."""
        discovery = await self.get_discovery_document()
        token_endpoint = discovery.get("token_endpoint")

        if not token_endpoint:
            raise OIDCError("Token endpoint not found in discovery document")

        data = {
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": settings.get_oidc_redirect_uri(),
            "client_id": settings.oidc_client_id,
            "client_secret": settings.oidc_client_secret,
        }

        async with httpx.AsyncClient() as client:
            response = await client.post(
                token_endpoint,
                data=data,
                timeout=10.0,
            )
            if response.status_code != 200:
                raise OIDCError(f"Token exchange failed: {response.text}")

            return response.json()

    async def get_user_info(self, access_token: str) -> OIDCUserInfo:
        """Fetch user info from the userinfo endpoint."""
        discovery = await self.get_discovery_document()
        userinfo_endpoint = discovery.get("userinfo_endpoint")

        if not userinfo_endpoint:
            raise OIDCError("Userinfo endpoint not found in discovery document")

        async with httpx.AsyncClient() as client:
            response = await client.get(
                userinfo_endpoint,
                headers={"Authorization": f"Bearer {access_token}"},
                timeout=10.0,
            )
            if response.status_code != 200:
                raise OIDCError(f"Failed to fetch user info: {response.text}")

            data = response.json()

        email = data.get("email")
        if not email:
            raise OIDCError("Email not provided by OIDC provider")

        # Extract groups from various possible claim names
        groups = (
            data.get("groups") or
            data.get("roles") or
            data.get("group") or
            []
        )
        if isinstance(groups, str):
            groups = [groups]

        return OIDCUserInfo(
            email=email,
            name=data.get("name") or data.get("preferred_username"),
            groups=groups,
        )

    def validate_domain(self, email: str) -> bool:
        """Check if email domain is allowed."""
        if not settings.oidc_allowed_domain:
            return True  # No domain restriction

        domain = email.split("@")[-1].lower()
        allowed = settings.oidc_allowed_domain.lower()
        return domain == allowed

    def is_admin_from_groups(self, groups: list[str]) -> bool:
        """Check if user should be admin based on group membership."""
        if not settings.oidc_admin_group:
            return False  # No admin group configured, all users are regular

        return settings.oidc_admin_group in groups


# Singleton instance
oidc_service = OIDCService()
