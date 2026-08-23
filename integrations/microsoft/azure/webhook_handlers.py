"""Adapt trusted provider webhooks into durable, provider-neutral signals."""

from dataclasses import dataclass
from datetime import datetime, timezone
from hashlib import sha256
from typing import Mapping

from integrations.google.google_drive.webhook import parse_notification as parse_google
from integrations.microsoft.onedrive.webhook import (
    parse_notifications as parse_onedrive,
    validation_response,
)
from repositories.change_notifications import ChangeSignal


@dataclass(frozen=True)
class WebhookResult:
    """Host-neutral HTTP response plus signals to enqueue before replying."""

    status_code: int
    body: str = ""
    content_type: str = "text/plain"
    signals: tuple[ChangeSignal, ...] = ()


def handle_onedrive_webhook(
    body: bytes,
    *,
    validation_token: str | None,
    expected_client_state: str,
    expected_subscription_id: str | None = None,
    received_at: datetime | None = None,
) -> WebhookResult:
    """Handle Graph endpoint validation or trusted change notifications."""
    if validation_token:
        response = validation_response(validation_token)
        return WebhookResult(
            response.status_code, response.body, response.content_type,
        )

    notifications = parse_onedrive(
        body,
        expected_client_state=expected_client_state,
        expected_subscription_id=expected_subscription_id,
    )
    timestamp = received_at or datetime.now(timezone.utc)
    body_identity = sha256(body).hexdigest()
    signals = tuple(
        ChangeSignal(
            "onedrive",
            f"{body_identity}:{index}:{notification.subscription_id}",
            timestamp,
        )
        for index, notification in enumerate(notifications)
    )
    return WebhookResult(202, signals=signals)


def handle_google_drive_webhook(
    headers: Mapping[str, str],
    *,
    expected_channel_token: str,
    expected_channel_id: str | None = None,
    expected_resource_id: str | None = None,
    received_at: datetime | None = None,
) -> WebhookResult:
    """Handle a trusted Google Drive sync or change signal."""
    notification = parse_google(
        headers,
        expected_channel_token=expected_channel_token,
        expected_channel_id=expected_channel_id,
        expected_resource_id=expected_resource_id,
    )
    if notification.is_sync:
        return WebhookResult(204)
    signal = ChangeSignal(
        "google_drive",
        notification.identity,
        received_at or datetime.now(timezone.utc),
    )
    return WebhookResult(202, signals=(signal,))
