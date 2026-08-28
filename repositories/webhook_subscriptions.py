"""Reconcile renewable cloud-drive notification subscriptions."""

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from functools import lru_cache
from typing import Literal

from common.config import read_toml
from integrations.google.google_drive.subscriptions import (
    create_changes_channel,
)
from integrations.microsoft.onedrive.client import GraphRequestError
from integrations.microsoft.onedrive.subscriptions import (
    create_subscription,
    folder_subscription_resource,
    list_subscriptions,
    renew_subscription,
)


SubscriptionActionName = Literal[
    "unchanged", "created", "adopted", "renewed", "replaced",
    "would_create", "would_adopt", "would_renew", "would_replace",
]


def _aware_utc(value: datetime) -> datetime:
    """Return an aware UTC datetime or reject ambiguous state."""
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("subscription timestamps must include a timezone")
    return value.astimezone(timezone.utc)


def _response_datetime(value: object, field_name: str) -> datetime:
    """Parse an ISO provider timestamp into aware UTC."""
    if not isinstance(value, str) or not value:
        raise ValueError(f"provider response is missing {field_name}")
    try:
        return _aware_utc(datetime.fromisoformat(value.replace("Z", "+00:00")))
    except ValueError as error:
        raise ValueError(f"provider returned invalid {field_name}") from error


@dataclass(frozen=True)
class ProviderSubscriptionState:
    """Provider-neutral durable state for one notification subscription."""

    provider: Literal["onedrive", "google_drive"]
    external_id: str
    expires_at: datetime
    notification_url: str
    resource_id: str | None = None
    cursor: str | None = None
    target_resource: str | None = None

    def __post_init__(self) -> None:
        if self.provider not in {"onedrive", "google_drive"}:
            raise ValueError(f"unsupported subscription provider: {self.provider!r}")
        if not self.external_id:
            raise ValueError("external_id must not be empty")
        if not self.notification_url.startswith("https://"):
            raise ValueError("notification_url must use HTTPS")
        object.__setattr__(self, "expires_at", _aware_utc(self.expires_at))


@dataclass(frozen=True)
class SubscriptionPolicy:
    """Renewal lead times for short-lived provider subscriptions."""

    onedrive_renew_before: timedelta
    google_drive_replace_before: timedelta

    def __post_init__(self) -> None:
        if self.onedrive_renew_before <= timedelta(0):
            raise ValueError("OneDrive renewal lead time must be positive")
        if self.google_drive_replace_before <= timedelta(0):
            raise ValueError("Google Drive replacement lead time must be positive")


@dataclass(frozen=True)
class SubscriptionAction:
    """Safe operational result without provider tokens or private identifiers."""

    provider: Literal["onedrive", "google_drive"]
    action: SubscriptionActionName
    expires_at: datetime | None


def _positive_days(value: object, field_name: str) -> timedelta:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or value <= 0:
        raise ValueError(
            f"webhooks.drive_changes.subscriptions.{field_name} must be positive"
        )
    return timedelta(days=value)


@lru_cache(maxsize=1)
def get_subscription_policy() -> SubscriptionPolicy:
    """Load provider renewal lead times from checked-in configuration."""
    try:
        config = read_toml("webhooks")["drive_changes"]["subscriptions"]
        return SubscriptionPolicy(
            onedrive_renew_before=_positive_days(
                config["onedrive_renew_before_days"],
                "onedrive_renew_before_days",
            ),
            google_drive_replace_before=_positive_days(
                config["google_drive_replace_before_days"],
                "google_drive_replace_before_days",
            ),
        )
    except (KeyError, TypeError) as error:
        raise ValueError(
            "config/webhooks.toml is missing the subscription renewal policy"
        ) from error


def _onedrive_state(response: dict, notification_url: str) -> ProviderSubscriptionState:
    external_id = response.get("id")
    if not isinstance(external_id, str) or not external_id:
        raise ValueError("Microsoft Graph returned no subscription ID")
    resource = response.get("resource")
    if not isinstance(resource, str) or not resource:
        raise ValueError("Microsoft Graph returned no subscription resource")
    return ProviderSubscriptionState(
        provider="onedrive",
        external_id=external_id,
        expires_at=_response_datetime(
            response.get("expirationDateTime"), "expirationDateTime"
        ),
        notification_url=notification_url,
        target_resource=resource,
    )


def _google_state(response: dict, notification_url: str) -> ProviderSubscriptionState:
    external_id = response.get("id")
    resource_id = response.get("resourceId")
    cursor = response.get("pageToken")
    expiration = response.get("expiration")
    if not isinstance(external_id, str) or not external_id:
        raise ValueError("Google Drive returned no channel ID")
    if not isinstance(resource_id, str) or not resource_id:
        raise ValueError("Google Drive returned no channel resource ID")
    if not isinstance(cursor, str) or not cursor:
        raise ValueError("Google Drive returned no channel cursor")
    try:
        expires_at = datetime.fromtimestamp(int(expiration) / 1000, timezone.utc)
    except (TypeError, ValueError, OSError) as error:
        raise ValueError("Google Drive returned an invalid channel expiration") from error
    return ProviderSubscriptionState(
        provider="google_drive",
        external_id=external_id,
        resource_id=resource_id,
        cursor=cursor,
        expires_at=expires_at,
        notification_url=notification_url,
    )


def reconcile_onedrive_subscription(
    current: ProviderSubscriptionState | None,
    notification_url: str,
    client_state: str,
    *,
    folder_id: str | None = None,
    now: datetime | None = None,
    apply: bool = False,
    policy: SubscriptionPolicy | None = None,
) -> tuple[ProviderSubscriptionState | None, SubscriptionAction]:
    """Adopt, create, or renew the OneDrive subscription without gaps."""
    current_time = _aware_utc(now or datetime.now(timezone.utc))
    selected_policy = policy or get_subscription_policy()
    target_resource = folder_subscription_resource(folder_id)

    candidates = [
        item for item in list_subscriptions()
        if item.get("notificationUrl") == notification_url
        and item.get("resource") == target_resource
    ]
    matching_response = next(
        (
            item for item in candidates
            if current and item.get("id") == current.external_id
        ),
        None,
    )
    matching = (
        _onedrive_state(matching_response, notification_url)
        if matching_response
        else None
    )

    if matching is None and candidates:
        candidate = max(
            candidates,
            key=lambda item: _response_datetime(
                item.get("expirationDateTime"), "expirationDateTime"
            ),
        )
        adopted = _onedrive_state(candidate, notification_url)
        action = "adopted" if apply else "would_adopt"
        if adopted.expires_at - current_time > selected_policy.onedrive_renew_before:
            return (adopted if apply else current), SubscriptionAction(
                "onedrive", action, adopted.expires_at
            )
        matching = adopted

    if matching is None:
        if not apply:
            return current, SubscriptionAction("onedrive", "would_create", None)
        created = _onedrive_state(
            create_subscription(
                notification_url,
                client_state,
                folder_id=folder_id,
            ),
            notification_url,
        )
        return created, SubscriptionAction("onedrive", "created", created.expires_at)

    if matching.expires_at - current_time > selected_policy.onedrive_renew_before:
        return matching, SubscriptionAction("onedrive", "unchanged", matching.expires_at)
    if not apply:
        return current, SubscriptionAction(
            "onedrive", "would_renew", matching.expires_at
        )
    try:
        renewed = _onedrive_state(
            renew_subscription(matching.external_id), notification_url
        )
    except GraphRequestError as error:
        if "HTTP 404" not in str(error):
            raise
        renewed = _onedrive_state(
            create_subscription(
                notification_url,
                client_state,
                folder_id=folder_id,
            ),
            notification_url,
        )
        return renewed, SubscriptionAction(
            "onedrive", "replaced", renewed.expires_at
        )
    return renewed, SubscriptionAction("onedrive", "renewed", renewed.expires_at)


def reconcile_google_drive_channel(
    current: ProviderSubscriptionState | None,
    notification_url: str,
    channel_token: str,
    *,
    now: datetime | None = None,
    apply: bool = False,
    policy: SubscriptionPolicy | None = None,
) -> tuple[ProviderSubscriptionState | None, SubscriptionAction]:
    """Create or replace the Google channel before its fixed expiration."""
    current_time = _aware_utc(now or datetime.now(timezone.utc))
    selected_policy = policy or get_subscription_policy()
    matching = current if (
        current
        and current.provider == "google_drive"
        and current.notification_url == notification_url
        and current.resource_id
    ) else None

    if matching and (
        matching.expires_at - current_time
        > selected_policy.google_drive_replace_before
    ):
        return matching, SubscriptionAction(
            "google_drive", "unchanged", matching.expires_at
        )

    action: SubscriptionActionName = "created" if matching is None else "replaced"
    if not apply:
        preview_action: SubscriptionActionName = (
            "would_create" if matching is None else "would_replace"
        )
        return current, SubscriptionAction(
            "google_drive",
            preview_action,
            matching.expires_at if matching else None,
        )

    created = _google_state(
        create_changes_channel(notification_url, channel_token),
        notification_url,
    )
    return created, SubscriptionAction("google_drive", action, created.expires_at)
