"""Shared local OAuth 2.0 with PKCE for Google API integrations."""

from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Any
from urllib.error import HTTPError
from urllib.parse import parse_qs, urlencode, urlparse
from urllib.request import Request, urlopen
import base64
import hashlib
import json
import os
import secrets as secure_secrets
import time
import webbrowser

from common.config import read_toml


TOKEN_CACHES = {
    "google_drive": Path(os.environ.get(
        "YEAR_END_GOOGLE_DRIVE_TOKEN_FILE",
        ".secrets/auths/tokens/gdrive/token.json",
    )),
    "gmail": Path(".secrets/auths/tokens/gmail/token.json"),
    "google_calendar": Path(".secrets/auths/tokens/google_calendar/token.json"),
}


class GoogleAuthError(RuntimeError):
    """Raised when Google cannot issue a usable access token."""


@dataclass(frozen=True)
class GoogleSettings:
    client_id: str
    client_secret: str
    authorize_endpoint: str
    token_endpoint: str
    scopes: tuple[str, ...]


def load_settings(service: str) -> GoogleSettings:
    """Load shared Google credentials and service-specific scopes."""
    if service not in TOKEN_CACHES:
        raise ValueError(f"Unsupported Google service: {service!r}")

    from common.secret import secrets

    desktop = secrets["google"]["desktop"]
    api_config = read_toml("api")
    return GoogleSettings(
        client_id=desktop["client_id"],
        client_secret=desktop["client_secret"],
        authorize_endpoint=api_config["google"]["urls"]["authorize"],
        token_endpoint=api_config["google"]["urls"]["token"],
        scopes=tuple(api_config[service]["oauth"]["scopes"]),
    )


def _read_cache(token_path: Path) -> dict[str, Any] | None:
    if not token_path.exists():
        return None
    return json.loads(token_path.read_text(encoding="utf-8"))


def _write_cache(token: dict[str, Any], token_path: Path) -> None:
    token_path.parent.mkdir(parents=True, exist_ok=True)
    token_path.write_text(json.dumps(token, indent=2), encoding="utf-8")


def _post_form(token_endpoint: str, form: dict[str, str]) -> dict[str, Any]:
    request = Request(token_endpoint, data=urlencode(form).encode("utf-8"),
                      headers={"Content-Type": "application/x-www-form-urlencoded"}, method="POST")
    try:
        with urlopen(request, timeout=30) as response:
            return json.load(response)
    except HTTPError as error:
        body = error.read().decode("utf-8", errors="replace")
        try:
            detail = json.loads(body).get("error_description") or body
        except json.JSONDecodeError:
            detail = body
        raise GoogleAuthError(f"Google token request failed (HTTP {error.code}): {detail}") from error
    except Exception as error:
        raise GoogleAuthError(f"Google token request failed: {error}") from error


def _create_pkce() -> tuple[str, str]:
    verifier = secure_secrets.token_urlsafe(64)
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode("ascii")).digest()).decode("ascii").rstrip("=")
    return verifier, challenge


def _wait_for_callback(port: int, expected_state: str, authorization_url: str) -> str:
    result: dict[str, str] = {}

    class CallbackHandler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802 - required handler name
            query = parse_qs(urlparse(self.path).query)
            if query.get("state", [""])[0] != expected_state:
                self.send_response(409)
                self.end_headers()
                return
            result["code"] = query.get("code", [""])[0]
            result["error"] = query.get("error", [""])[0]
            result["error_description"] = query.get("error_description", [""])[0]
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(b"<h1>Google authorization complete.</h1><p>You can close this tab.</p>")

        def log_message(self, _format: str, *_args: object) -> None:
            return

    server = HTTPServer(("127.0.0.1", port), CallbackHandler)
    server.timeout = 300
    try:
        webbrowser.open(authorization_url)
        server.handle_request()
    finally:
        server.server_close()

    if result.get("error"):
        raise GoogleAuthError(result.get("error_description") or result["error"])
    if not result.get("code"):
        raise GoogleAuthError("Google sign-in did not return an authorization code.")
    return result["code"]


def _cache_has_scopes(cached: dict[str, Any], scopes: tuple[str, ...], *, allow_legacy: bool) -> bool:
    granted = cached.get("granted_scopes") or cached.get("scope")
    if not granted:
        return allow_legacy
    granted_scopes = set(granted.split()) if isinstance(granted, str) else set(granted)
    return set(scopes).issubset(granted_scopes)


def get_access_token(service: str, *, force_login: bool = False, token_path: Path | None = None) -> str:
    """Return a separately cached, least-privilege token for a Google service."""
    settings = load_settings(service)
    cache_path = token_path or TOKEN_CACHES[service]
    cached = _read_cache(cache_path)
    has_scopes = bool(cached and _cache_has_scopes(cached, settings.scopes, allow_legacy=service == "google_drive"))
    if cached and has_scopes and not force_login and cached.get("expires_at", 0) > time.time() + 60:
        return cached["access_token"]
    if cached and has_scopes and not force_login and cached.get("refresh_token"):
        refreshed = _post_form(settings.token_endpoint, {
            "client_id": settings.client_id, "client_secret": settings.client_secret,
            "refresh_token": cached["refresh_token"], "grant_type": "refresh_token",
        })
        refreshed["refresh_token"] = cached["refresh_token"]
        refreshed["granted_scopes"] = list(settings.scopes)
        refreshed["expires_at"] = int(time.time()) + int(refreshed.get("expires_in", 0))
        _write_cache(refreshed, cache_path)
        return refreshed["access_token"]

    port_reservation = HTTPServer(("127.0.0.1", 0), BaseHTTPRequestHandler)
    port = port_reservation.server_port
    port_reservation.server_close()
    redirect_uri = f"http://127.0.0.1:{port}"
    state = secure_secrets.token_urlsafe(32)
    verifier, challenge = _create_pkce()
    query = urlencode({
        "client_id": settings.client_id, "redirect_uri": redirect_uri, "response_type": "code",
        "scope": " ".join(settings.scopes), "access_type": "offline", "prompt": "consent",
        "state": state, "code_challenge": challenge, "code_challenge_method": "S256",
    })
    print(f"Opening Google sign-in for {service}. Complete sign-in within 5 minutes.")
    code = _wait_for_callback(port, state, f"{settings.authorize_endpoint}?{query}")
    token = _post_form(settings.token_endpoint, {
        "client_id": settings.client_id, "client_secret": settings.client_secret, "code": code,
        "code_verifier": verifier, "grant_type": "authorization_code", "redirect_uri": redirect_uri,
    })
    if "access_token" not in token:
        raise GoogleAuthError(token.get("error_description", "Google did not issue an access token."))
    token["granted_scopes"] = list(settings.scopes)
    token["expires_at"] = int(time.time()) + int(token.get("expires_in", 0))
    _write_cache(token, cache_path)
    return token["access_token"]
