"""Authenticate as the repository's narrowly scoped GitHub App installation."""

from datetime import datetime, timedelta, timezone
from typing import Any
from urllib.error import HTTPError
from urllib.parse import quote
from urllib.request import Request, urlopen
import json

from common.config import read_toml


class GitHubAuthenticationError(RuntimeError):
    """Raised when GitHub App authentication does not produce a usable token."""


def _api_url() -> str:
    """Return the configured GitHub REST API base URL."""
    return read_toml("api")["github"]["urls"]["api"].rstrip("/")


def create_app_jwt(
    app_id: str,
    private_key: str,
    *,
    now: datetime | None = None,
) -> str:
    """Create a short-lived RS256 assertion for one GitHub App."""
    if not app_id.strip() or not private_key.strip():
        raise ValueError("app_id and private_key must not be empty")
    issued_at = now or datetime.now(timezone.utc)
    if issued_at.tzinfo is None or issued_at.utcoffset() is None:
        raise ValueError("now must include a timezone")
    try:
        import jwt
    except ImportError as error:
        raise GitHubAuthenticationError(
            "PyJWT with its crypto extra is required for GitHub App authentication"
        ) from error

    normalized_key = private_key.replace("\\n", "\n")
    return jwt.encode(
        {
            "iat": int((issued_at - timedelta(seconds=60)).timestamp()),
            "exp": int((issued_at + timedelta(minutes=9)).timestamp()),
            "iss": app_id,
        },
        normalized_key,
        algorithm="RS256",
    )


def get_installation_token(
    app_id: str,
    installation_id: str,
    private_key: str,
) -> str:
    """Exchange a GitHub App assertion for an installation access token."""
    if not installation_id.strip():
        raise ValueError("installation_id must not be empty")
    app_jwt = create_app_jwt(app_id, private_key)
    request = Request(
        f"{_api_url()}/app/installations/{quote(installation_id, safe='')}/access_tokens",
        data=b"{}",
        headers={
            "Authorization": f"Bearer {app_jwt}",
            "Accept": "application/vnd.github+json",
            "Content-Type": "application/json",
            "User-Agent": "year-end-automation",
            "X-GitHub-Api-Version": "2022-11-28",
        },
        method="POST",
    )
    try:
        with urlopen(request, timeout=30) as response:
            payload: dict[str, Any] = json.load(response)
    except HTTPError as error:
        body = error.read().decode("utf-8", errors="replace")
        raise GitHubAuthenticationError(
            f"GitHub installation authentication returned HTTP {error.code}: {body}"
        ) from error
    except Exception as error:
        raise GitHubAuthenticationError(
            f"GitHub installation authentication failed: {error}"
        ) from error

    token = payload.get("token")
    if not isinstance(token, str) or not token:
        raise GitHubAuthenticationError(
            "GitHub did not return an installation access token"
        )
    return token
