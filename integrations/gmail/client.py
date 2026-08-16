"""Minimal Gmail client for constructing and explicitly sending messages."""

from email.message import EmailMessage
from typing import Any, Iterable
from urllib.error import HTTPError
from urllib.request import Request, urlopen
import base64
import json

from common.config import read_toml
from integrations.gmail.auth import get_access_token


class GmailRequestError(RuntimeError):
    """Raised when Gmail rejects a request."""


def _api_url() -> str:
    """Return the configured Gmail API base URL."""
    return read_toml("api")["gmail"]["urls"]["api"]


def _post(path: str, payload: dict[str, Any], *, access_token: str) -> dict[str, Any]:
    request = Request(f"{_api_url()}{path}", data=json.dumps(payload).encode("utf-8"),
                      headers={"Authorization": f"Bearer {access_token}", "Accept": "application/json",
                               "Content-Type": "application/json"}, method="POST")
    try:
        with urlopen(request, timeout=30) as response:
            return json.load(response)
    except HTTPError as error:
        body = error.read().decode("utf-8", errors="replace")
        raise GmailRequestError(f"Gmail API returned HTTP {error.code}: {body}") from error
    except Exception as error:
        raise GmailRequestError(f"Gmail API request failed: {error}") from error


def build_message(recipients: str | Iterable[str], subject: str, body: str, *, sender: str | None = None) -> str:
    """Build a base64url-encoded plain-text MIME message without sending it."""
    recipient_list = [recipients] if isinstance(recipients, str) else list(recipients)
    if not recipient_list or any(not address.strip() for address in recipient_list):
        raise ValueError("At least one non-empty recipient is required")
    message = EmailMessage()
    message["To"] = ", ".join(recipient_list)
    message["Subject"] = subject
    if sender:
        message["From"] = sender
    message.set_content(body)
    return base64.urlsafe_b64encode(message.as_bytes()).decode("ascii").rstrip("=")


def send_message(recipients: str | Iterable[str], subject: str, body: str, *, sender: str | None = None,
                 force_login: bool = False) -> dict[str, Any]:
    """Send one explicitly supplied message as the authorized Gmail user."""
    raw_message = build_message(recipients, subject, body, sender=sender)
    return _post("/users/me/messages/send", {"raw": raw_message},
                 access_token=get_access_token(force_login=force_login))
