"""Least-privilege Gmail authorization using the shared Google OAuth flow."""

from pathlib import Path

from integrations.google.auth import GoogleAuthError, TOKEN_CACHES, get_access_token as _get_access_token


TOKEN_CACHE = TOKEN_CACHES["gmail"]


def get_access_token(*, force_login: bool = False, token_path: Path = TOKEN_CACHE) -> str:
    """Return a Gmail-send token from its separate credential cache."""
    return _get_access_token("gmail", force_login=force_login, token_path=token_path)
