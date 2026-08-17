"""Gmail client for constructing, drafting, and explicitly sending messages."""

from email.message import EmailMessage
from typing import Any, Iterable
from urllib.error import HTTPError
from urllib.request import Request, urlopen
import base64
import json

from common.config import read_toml
from integrations.google.auth import get_access_token


class GmailRequestError(RuntimeError):
    """Raised when Gmail rejects a request."""


def _api_url() -> str:
    """Return the configured Gmail API base URL."""
    return read_toml("api")["gmail"]["urls"]["api"]


def _request(
    method: str,
    path: str,
    payload: dict[str, Any],
    *,
    access_token: str,
) -> dict[str, Any]:
    """Make one authenticated Gmail JSON request."""
    request = Request(f"{_api_url()}{path}", data=json.dumps(payload).encode("utf-8"),
                      headers={"Authorization": f"Bearer {access_token}", "Accept": "application/json",
                               "Content-Type": "application/json"}, method=method)
    try:
        with urlopen(request, timeout=30) as response:
            return json.load(response)
    except HTTPError as error:
        body = error.read().decode("utf-8", errors="replace")
        raise GmailRequestError(f"Gmail API returned HTTP {error.code}: {body}") from error
    except Exception as error:
        raise GmailRequestError(f"Gmail API request failed: {error}") from error


def _addresses(value: str | Iterable[str] | None) -> list[str]:
    """Normalize one optional address header."""
    addresses = [] if value is None else ([value] if isinstance(value, str) else list(value))
    if any(not address.strip() for address in addresses):
        raise ValueError("Email addresses must not be empty")
    return addresses


def build_message(
    recipients: str | Iterable[str] | None,
    subject: str,
    body: str,
    *,
    cc: str | Iterable[str] | None = None,
    bcc: str | Iterable[str] | None = None,
    html_body: str | None = None,
    sender: str | None = None,
) -> str:
    """Build a base64url-encoded MIME message without sending it."""
    recipient_list = _addresses(recipients)
    cc_list = _addresses(cc)
    bcc_list = _addresses(bcc)
    if not recipient_list and not cc_list and not bcc_list:
        raise ValueError("At least one recipient is required")
    message = EmailMessage()
    if recipient_list:
        message["To"] = ", ".join(recipient_list)
    if cc_list:
        message["Cc"] = ", ".join(cc_list)
    if bcc_list:
        message["Bcc"] = ", ".join(bcc_list)
    message["Subject"] = subject
    if sender:
        message["From"] = sender
    message.set_content(body)
    if html_body is not None:
        message.add_alternative(html_body, subtype="html")
    return base64.urlsafe_b64encode(message.as_bytes()).decode("ascii").rstrip("=")


def send_message(recipients: str | Iterable[str], subject: str, body: str, *, sender: str | None = None,
                 force_login: bool = False) -> dict[str, Any]:
    """Send one explicitly supplied message as the authorized Gmail user."""
    raw_message = build_message(recipients, subject, body, sender=sender)
    return _request("POST", "/users/me/messages/send", {"raw": raw_message},
                    access_token=get_access_token("gmail", force_login=force_login))


def create_draft(
    recipients: str | Iterable[str] | None,
    subject: str,
    body: str,
    *,
    cc: str | Iterable[str] | None = None,
    bcc: str | Iterable[str] | None = None,
    html_body: str | None = None,
    sender: str | None = None,
    force_login: bool = False,
) -> dict[str, Any]:
    """Create one unsent Gmail draft for explicit review."""
    raw_message = build_message(
        recipients,
        subject,
        body,
        cc=cc,
        bcc=bcc,
        html_body=html_body,
        sender=sender,
    )
    return _request(
        "POST",
        "/users/me/drafts",
        {"message": {"raw": raw_message}},
        access_token=get_access_token("gmail", force_login=force_login),
    )


def update_draft(
    draft_id: str,
    recipients: str | Iterable[str],
    subject: str,
    body: str,
    *,
    sender: str | None = None,
) -> dict[str, Any]:
    """Replace one existing Gmail draft without sending it."""
    if not draft_id.strip():
        raise ValueError("draft_id must not be empty")
    raw_message = build_message(recipients, subject, body, sender=sender)
    return _request(
        "PUT",
        f"/users/me/drafts/{draft_id}",
        {"id": draft_id, "message": {"raw": raw_message}},
        access_token=get_access_token("gmail"),
    )


def send_draft(draft_id: str) -> dict[str, Any]:
    """Send an existing reviewed Gmail draft by its stable draft ID."""
    if not draft_id.strip():
        raise ValueError("draft_id must not be empty")
    return _request(
        "POST",
        "/users/me/drafts/send",
        {"id": draft_id},
        access_token=get_access_token("gmail"),
    )
