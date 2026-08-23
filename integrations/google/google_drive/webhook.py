"""Validate host-neutral Google Drive push-notification headers."""

from collections.abc import Mapping
from dataclasses import dataclass
from secrets import compare_digest


class GoogleDriveWebhookError(ValueError):
    """Raised when a Google Drive notification cannot be trusted or parsed."""


@dataclass(frozen=True)
class GoogleDriveNotification:
    """Trusted signal that a watched Google Drive resource changed."""

    channel_id: str
    resource_id: str
    resource_state: str
    message_number: int
    changed: str | None = None
    channel_expiration: str | None = None

    @property
    def identity(self) -> str:
        """Return a stable per-channel notification identity."""
        return f"{self.channel_id}:{self.message_number}"

    @property
    def is_sync(self) -> bool:
        """Return whether this is the channel-creation handshake signal."""
        return self.resource_state == "sync"


def parse_notification(
    headers: Mapping[str, str],
    *,
    expected_channel_token: str,
    expected_channel_id: str | None = None,
    expected_resource_id: str | None = None,
) -> GoogleDriveNotification:
    """Validate Google headers and return their notification signal."""
    if not expected_channel_token:
        raise ValueError("expected_channel_token must not be empty")
    normalized = {name.casefold(): value for name, value in headers.items()}

    channel_token = normalized.get("x-goog-channel-token")
    if not isinstance(channel_token, str) or not compare_digest(
        channel_token, expected_channel_token
    ):
        raise GoogleDriveWebhookError("The Google Drive channel token does not match")

    channel_id = normalized.get("x-goog-channel-id")
    resource_id = normalized.get("x-goog-resource-id")
    resource_state = normalized.get("x-goog-resource-state")
    message_number = normalized.get("x-goog-message-number")
    if not channel_id or not resource_id or not resource_state or not message_number:
        raise GoogleDriveWebhookError(
            "The Google Drive notification is missing required headers"
        )
    if expected_channel_id and not compare_digest(channel_id, expected_channel_id):
        raise GoogleDriveWebhookError("The Google Drive channel ID does not match")
    if expected_resource_id and not compare_digest(resource_id, expected_resource_id):
        raise GoogleDriveWebhookError("The Google Drive resource ID does not match")
    if not message_number.isdigit() or int(message_number) < 1:
        raise GoogleDriveWebhookError(
            "The Google Drive message number is not a positive integer"
        )

    return GoogleDriveNotification(
        channel_id=channel_id,
        resource_id=resource_id,
        resource_state=resource_state,
        message_number=int(message_number),
        changed=normalized.get("x-goog-changed"),
        channel_expiration=normalized.get("x-goog-channel-expiration"),
    )
