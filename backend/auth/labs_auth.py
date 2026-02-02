"""YouWare Labs auth helpers for OAuth code flow."""

from __future__ import annotations

import os
import secrets
import time
from dataclasses import dataclass
import asyncio
import logging
from typing import Any, Optional

import httpx
import jwt
from jwt import PyJWTError


ALLOWED_STATUSES = {"approved", "not_required"}
PUBLIC_KEY_TTL_SECONDS = int(os.getenv("LABS_PUBLIC_KEY_TTL", "86400"))
logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class LabsAuthConfig:
    project_id: str
    labs_host: str
    public_base_url: Optional[str]
    cookie_name: str
    state_cookie_name: str
    next_cookie_name: str
    cookie_samesite: str
    cookie_secure: bool

    @property
    def labs_api(self) -> str:
        return f"{self.labs_host}/api/labs"

    @property
    def labs_authorize_url(self) -> str:
        return f"{self.labs_host}/labs/authorize"


def load_config() -> LabsAuthConfig:
    labs_env = os.getenv("LABS_ENV") or os.getenv("NODE_ENV") or "production"
    if labs_env == "production":
        labs_host = "https://www.youware.com"
    else:
        labs_host = "https://staging.youware.com"

    labs_host = os.getenv("LABS_HOST", labs_host).rstrip("/")
    project_id = os.getenv("LABS_PROJECT_ID", "")
    public_base_url = os.getenv("PUBLIC_BASE_URL")
    cookie_name = os.getenv("LABS_TOKEN_COOKIE", "labs_token")
    state_cookie_name = os.getenv("LABS_STATE_COOKIE", "labs_oauth_state")
    next_cookie_name = os.getenv("LABS_NEXT_COOKIE", "labs_oauth_next")
    cookie_samesite = os.getenv("LABS_COOKIE_SAMESITE", "lax").lower()
    cookie_secure_env = os.getenv("LABS_COOKIE_SECURE")
    if cookie_secure_env is None:
        cookie_secure = labs_env == "production"
    else:
        cookie_secure = cookie_secure_env.lower() == "true"

    return LabsAuthConfig(
        project_id=project_id,
        labs_host=labs_host,
        public_base_url=public_base_url,
        cookie_name=cookie_name,
        state_cookie_name=state_cookie_name,
        next_cookie_name=next_cookie_name,
        cookie_samesite=cookie_samesite,
        cookie_secure=cookie_secure,
    )


class PublicKeyCache:
    def __init__(self) -> None:
        self._public_key: Optional[str] = None
        self._expires_at: float = 0.0
        self._lock = asyncio.Lock()

    async def get(self, config: LabsAuthConfig) -> str:
        now = time.time()
        if self._public_key and now < self._expires_at:
            return self._public_key

        async with self._lock:
            now = time.time()
            if self._public_key and now < self._expires_at:
                return self._public_key

            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(f"{config.labs_api}/public-key")
                response.raise_for_status()
                payload = response.json()
                if payload.get("code") != 0:
                    raise RuntimeError(f"Failed to fetch public key: {payload.get('message')}")
                public_key = payload["data"]["public_key"]

            self._public_key = public_key
            self._expires_at = now + PUBLIC_KEY_TTL_SECONDS
            return public_key


_public_key_cache = PublicKeyCache()


def build_redirect_uri(config: LabsAuthConfig, request_base_url: str) -> str:
    """Build the OAuth callback redirect URI."""
    base_url = (config.public_base_url or request_base_url).rstrip("/")
    return f"{base_url}/api/labs/callback"


def sanitize_next_url(next_url: Optional[str]) -> str:
    """Sanitize the next URL to prevent open redirects."""
    if not next_url:
        return "/"
    if next_url.startswith("/") and not next_url.startswith("//"):
        return next_url
    return "/"


def generate_state() -> str:
    """Generate a cryptographically secure state token for CSRF protection."""
    return secrets.token_urlsafe(32)


async def exchange_code_for_token(
    config: LabsAuthConfig,
    code: str,
    redirect_uri: str,
) -> str:
    """Exchange an authorization code for an access token."""
    async with httpx.AsyncClient(timeout=10.0) as client:
        payload = {
            "code": code,
            "redirect_uri": redirect_uri,
        }
        if config.project_id:
            payload["project_id"] = config.project_id

        response = await client.post(
            f"{config.labs_api}/token",
            json=payload,
        )
        if response.is_error:
            body = response.text
            logger.error(
                "Labs token exchange failed: status=%s body=%s",
                response.status_code,
                body,
            )
            response.raise_for_status()

        payload = response.json()
        if payload.get("code") != 0:
            raise RuntimeError(payload.get("message", "Token exchange failed"))
        return payload["data"]["token"]


async def verify_token_local(
    config: LabsAuthConfig,
    token: str,
) -> tuple[Optional[dict[str, Any]], Optional[str]]:
    """
    Verify a JWT token locally using the cached public key.
    
    Returns:
        tuple: (payload, error) - If error is not None, payload is None.
    """
    try:
        public_key = await _public_key_cache.get(config)
        payload = jwt.decode(token, public_key, algorithms=["RS256"])
    except PyJWTError as e:
        return None, f"JWT decode failed: {e}"
    except Exception as e:
        return None, f"Public key fetch or decode error: {e}"

    project_id = payload.get("project_id")
    status = payload.get("status")

    if project_id != config.project_id:
        return None, f"project_id mismatch: token='{project_id}', config='{config.project_id}'"
    if status not in ALLOWED_STATUSES:
        return None, f"status '{status}' not in {ALLOWED_STATUSES}"
    return payload, None
