"""Validate and parse host-neutral Microsoft Graph webhook requests."""

from dataclasses import dataclass
from secrets import compare_digest
from typing import Any
import json


class WebhookNotificationError(ValueError):
    """Raised when a OneDrive webhook payload cannot be trusted or parsed."""


@dataclass(frozen=True)
class ValidationResponse:
    """Host-neutral response required during Graph endpoint validation."""

    body: str
    status_code: int = 200
    content_type: str = "text/plain"


@dataclass(frozen=True)
class OneDriveNotification:
    """Trusted change or lifecycle signal from a OneDrive subscription."""

    subscription_id: str
    resource: str
    change_type: str | None = None
    lifecycle_event: str | None = None


def validation_response(validation_token: str | None) -> ValidationResponse:
    """Build the exact plain-text response Graph requires during registration."""
    if not validation_token:
        raise WebhookNotificationError("Microsoft Graph did not provide a validation token")
    return ValidationResponse(body=validation_token)


def _read_payload(payload: bytes | str | dict[str, Any]) -> dict[str, Any]:
    if isinstance(payload, dict):
        return payload
    try:
        decoded = payload.decode("utf-8") if isinstance(payload, bytes) else payload
        parsed = json.loads(decoded)
    except (UnicodeDecodeError, json.JSONDecodeError, TypeError) as error:
        raise WebhookNotificationError("The webhook body is not valid JSON") from error
    if not isinstance(parsed, dict):
        raise WebhookNotificationError("The webhook body must be a JSON object")
    return parsed


def parse_notifications(
    payload: bytes | str | dict[str, Any],
    *,
    expected_client_state: str,
    expected_subscription_id: str | None = None,
) -> list[OneDriveNotification]:
    """Return trusted notification signals after validating their shared secret."""
    if not expected_client_state:
        raise ValueError("expected_client_state must not be empty")

    entries = _read_payload(payload).get("value")
    if not isinstance(entries, list) or not entries:
        raise WebhookNotificationError("The webhook body contains no notifications")

    notifications = []
    seen = set()
    for entry in entries:
        if not isinstance(entry, dict):
            raise WebhookNotificationError("The webhook body contains a malformed notification")
        client_state = entry.get("clientState")
        if not isinstance(client_state, str) or not compare_digest(
            client_state, expected_client_state
        ):
            raise WebhookNotificationError("The notification client state does not match")

        subscription_id = entry.get("subscriptionId")
        resource = entry.get("resource")
        if not isinstance(subscription_id, str) or not subscription_id:
            raise WebhookNotificationError("The notification has no subscription ID")
        if expected_subscription_id and not compare_digest(
            subscription_id, expected_subscription_id
        ):
            raise WebhookNotificationError("The notification subscription ID does not match")
        if not isinstance(resource, str) or not resource:
            raise WebhookNotificationError("The notification has no resource")

        change_type = entry.get("changeType")
        lifecycle_event = entry.get("lifecycleEvent")
        if change_type is not None and not isinstance(change_type, str):
            raise WebhookNotificationError("The notification has an invalid change type")
        if lifecycle_event is not None and not isinstance(lifecycle_event, str):
            raise WebhookNotificationError("The notification has an invalid lifecycle event")

        notification = OneDriveNotification(
            subscription_id=subscription_id,
            resource=resource,
            change_type=change_type,
            lifecycle_event=lifecycle_event,
        )
        identity = (
            notification.subscription_id,
            notification.resource,
            notification.change_type,
            notification.lifecycle_event,
        )
        if identity not in seen:
            seen.add(identity)
            notifications.append(notification)
    return notifications
