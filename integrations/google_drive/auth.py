"""Compatibility wrapper for the shared Google OAuth implementation."""

from pathlib import Path

from integrations.google.auth import GoogleAuthError, TOKEN_CACHES, get_access_token as _get_access_token


TOKEN_CACHE = TOKEN_CACHES["google_drive"]


def get_access_token(*, force_login: bool = False, token_path: Path = TOKEN_CACHE) -> str:
    """Return a Google Drive token using the shared Google OAuth flow."""
    return _get_access_token("google_drive", force_login=force_login, token_path=token_path)
