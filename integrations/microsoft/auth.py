"""Shared local OAuth support for Microsoft product integrations."""

from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from threading import Event, Thread
from typing import Any
from urllib.error import HTTPError
from urllib.parse import parse_qs, urlencode, urlparse
from urllib.request import Request, urlopen
import json
import secrets as secure_secrets
import time
import webbrowser

from common.config import read_toml


TOKEN_CACHES = {
    "onedrive": Path(".secrets/auths/tokens/azure/token.json"),
}


class MicrosoftAuthError(RuntimeError):
    """Raised when Microsoft identity cannot issue a usable access token."""


@dataclass(frozen=True)
class MicrosoftSettings:
    client_id: str
    client_secret: str
    authorize_endpoint: str
    redirect_uri: str
    scopes: tuple[str, ...]

    @property
    def token_endpoint(self) -> str:
        return self.authorize_endpoint.rsplit("/authorize", 1)[0] + "/token"


def load_settings(service: str) -> MicrosoftSettings:
    """Load shared Microsoft credentials and product-specific scopes."""
    if service not in TOKEN_CACHES:
        raise ValueError(f"Unsupported Microsoft service: {service!r}")

    from common.secret import secrets
    api_config = read_toml("api")
    desktop = secrets["microsoft"]["desktop"]

    return MicrosoftSettings(
        client_id=desktop["client_id"],
        client_secret=desktop["client_secret"],
        authorize_endpoint=f"{api_config['microsoft']['urls']['identity']}/authorize",
        redirect_uri=api_config["microsoft"]["oauth"]["redirect_uri"],
        scopes=tuple(api_config[service]["oauth"]["scopes"]),
    )


def _read_cache(token_path: Path) -> dict[str, Any] | None:
    if not token_path.exists():
        return None
    with token_path.open(encoding="utf-8") as token_file:
        return json.load(token_file)


def _write_cache(token: dict[str, Any], token_path: Path) -> None:
    token_path.parent.mkdir(parents=True, exist_ok=True)
    with token_path.open("w", encoding="utf-8") as token_file:
        json.dump(token, token_file, indent=2)


def _post_form(url: str, form: dict[str, str]) -> dict[str, Any]:
    request = Request(
        url,
        data=urlencode(form).encode("utf-8"),
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        method="POST",
    )
    try:
        with urlopen(request, timeout=30) as response:
            return json.load(response)
    except HTTPError as error:
        # Microsoft returns an AADSTS error code and description in the response
        # body. It does not include the submitted client secret, so it is safe to
        # show this diagnostic to the local command user.
        body = error.read().decode("utf-8", errors="replace")
        try:
            detail = json.loads(body).get("error_description") or body
        except json.JSONDecodeError:
            detail = body
        raise MicrosoftAuthError(f"Microsoft token request failed (HTTP {error.code}): {detail}") from error
    except Exception as error:
        raise MicrosoftAuthError(f"Microsoft token request failed: {error}") from error


def _refresh_token(settings: MicrosoftSettings, cached_token: dict[str, Any]) -> dict[str, Any] | None:
    refresh_token = cached_token.get("refresh_token")
    if not refresh_token:
        return None
    response = _post_form(settings.token_endpoint, {
        "client_id": settings.client_id,
        "client_secret": settings.client_secret,
        "grant_type": "refresh_token",
        "refresh_token": refresh_token,
        "scope": " ".join(settings.scopes),
    })
    if "access_token" not in response:
        return None
    response["expires_at"] = int(time.time()) + int(response.get("expires_in", 0))
    response.setdefault("refresh_token", refresh_token)
    return response


def _wait_for_callback(redirect_uri: str, expected_state: str) -> str:
    parsed = urlparse(redirect_uri)
    if parsed.scheme != "http" or parsed.hostname not in {"localhost", "127.0.0.1"} or not parsed.port:
        raise MicrosoftAuthError("The redirect URI must be a localhost HTTP URL for this local client.")

    result: dict[str, str] = {}
    completed = Event()

    class CallbackHandler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802 - required handler name
            if urlparse(self.path).path != parsed.path:
                self.send_response(404)
                self.end_headers()
                return
            query = parse_qs(urlparse(self.path).query)
            callback_state = query.get("state", [""])[0]
            if callback_state != expected_state:
                self.send_response(409)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.end_headers()
                self.wfile.write(b"<h1>Stale OneDrive authorization response.</h1><p>Please return to the current sign-in tab.</p>")
                return
            result["code"] = query.get("code", [""])[0]
            result["state"] = callback_state
            result["error"] = query.get("error", [""])[0]
            result["error_description"] = query.get("error_description", [""])[0]
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(b"<h1>OneDrive authorization complete.</h1><p>You can close this tab.</p>")
            completed.set()

        def log_message(self, _format: str, *_args: object) -> None:
            return

    server = HTTPServer((parsed.hostname, parsed.port), CallbackHandler)
    def serve_callback() -> None:
        deadline = time.monotonic() + 300
        server.timeout = 1
        while not completed.is_set() and time.monotonic() < deadline:
            server.handle_request()

    callback_thread = Thread(target=serve_callback, daemon=True)
    callback_thread.start()
    callback_thread.join(timeout=305)
    server.server_close()

    if callback_thread.is_alive():
        raise MicrosoftAuthError("Timed out waiting for Microsoft sign-in (5 minutes).")
    if result.get("state") != expected_state:
        raise MicrosoftAuthError("Microsoft sign-in returned an invalid state value.")
    if result.get("error"):
        raise MicrosoftAuthError(result.get("error_description") or result["error"])
    if not result.get("code"):
        raise MicrosoftAuthError("Microsoft sign-in did not return an authorization code.")
    return result["code"]


def get_access_token(
    service: str,
    *,
    force_login: bool = False,
    token_path: Path | None = None,
) -> str:
    """Return a separately cached delegated token for a Microsoft product."""
    settings = load_settings(service)
    cache_path = token_path or TOKEN_CACHES[service]
    cached_token = _read_cache(cache_path)
    if cached_token and not force_login and cached_token.get("expires_at", 0) > time.time() + 60:
        return cached_token["access_token"]
    if cached_token and not force_login:
        refreshed_token = _refresh_token(settings, cached_token)
        if refreshed_token:
            _write_cache(refreshed_token, cache_path)
            return refreshed_token["access_token"]

    state = secure_secrets.token_urlsafe(32)
    query = urlencode({
        "client_id": settings.client_id,
        "response_type": "code",
        "redirect_uri": settings.redirect_uri,
        "response_mode": "query",
        "scope": " ".join(settings.scopes),
        "state": state,
    })
    authorization_url = f"{settings.authorize_endpoint}?{query}"
    print("Opening Microsoft sign-in in your default browser. Complete sign-in within 5 minutes.")
    webbrowser.open(authorization_url)
    code = _wait_for_callback(settings.redirect_uri, state)
    token = _post_form(settings.token_endpoint, {
        "client_id": settings.client_id,
        "client_secret": settings.client_secret,
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": settings.redirect_uri,
        "scope": " ".join(settings.scopes),
    })
    if "access_token" not in token:
        raise MicrosoftAuthError(token.get("error_description", "Microsoft did not issue an access token."))
    token["expires_at"] = int(time.time()) + int(token.get("expires_in", 0))
    _write_cache(token, cache_path)
    return token["access_token"]
