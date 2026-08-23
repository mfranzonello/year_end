"""Manage OneDrive change subscriptions and retrieve delta changes."""

from datetime import datetime, timedelta, timezone
from typing import Any
from urllib.parse import quote, urlparse

from integrations.microsoft.auth import get_access_token
from integrations.microsoft.onedrive.client import (
    GraphRequestError, _delete, _get, _get_url, _patch, _post,
)


DEFAULT_SUBSCRIPTION_LIFETIME = timedelta(days=29)
DELTA_FIELDS = (
    "id,name,size,file,folder,video,deleted,parentReference,lastModifiedDateTime"
)


def _graph_datetime(value: datetime) -> str:
    """Return an aware UTC datetime in the format Microsoft Graph accepts."""
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("Microsoft Graph datetimes must include a timezone")
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def folder_subscription_resource(folder_id: str | None = None) -> str:
    """Return the Graph subscription resource for a personal OneDrive folder."""
    if folder_id is None:
        return "me/drive/root"
    if not folder_id.strip():
        raise ValueError("folder_id must not be empty")
    return f"me/drive/items/{quote(folder_id, safe='')}"


def create_subscription(
    notification_url: str,
    client_state: str,
    *,
    folder_id: str | None = None,
    expires_at: datetime | None = None,
) -> dict[str, Any]:
    """Create a basic change notification subscription for a OneDrive folder."""
    parsed_notification_url = urlparse(notification_url)
    if parsed_notification_url.scheme.lower() != "https" or not parsed_notification_url.netloc:
        raise ValueError("notification_url must use HTTPS")
    if not client_state:
        raise ValueError("client_state must not be empty")

    expiration = expires_at or datetime.now(timezone.utc) + DEFAULT_SUBSCRIPTION_LIFETIME
    return _post(
        "/subscriptions",
        {
            "changeType": "updated",
            "notificationUrl": notification_url,
            "resource": folder_subscription_resource(folder_id),
            "expirationDateTime": _graph_datetime(expiration),
            "clientState": client_state,
            "latestSupportedTlsVersion": "v1_2",
        },
        access_token=get_access_token("onedrive"),
    )


def renew_subscription(
    subscription_id: str,
    *,
    expires_at: datetime | None = None,
) -> dict[str, Any]:
    """Extend an existing OneDrive subscription before it expires."""
    if not subscription_id.strip():
        raise ValueError("subscription_id must not be empty")
    expiration = expires_at or datetime.now(timezone.utc) + DEFAULT_SUBSCRIPTION_LIFETIME
    encoded_id = quote(subscription_id, safe="")
    return _patch(
        f"/subscriptions/{encoded_id}",
        {"expirationDateTime": _graph_datetime(expiration)},
        access_token=get_access_token("onedrive"),
    )


def delete_subscription(subscription_id: str) -> None:
    """Delete a OneDrive change notification subscription."""
    if not subscription_id.strip():
        raise ValueError("subscription_id must not be empty")
    encoded_id = quote(subscription_id, safe="")
    _delete(
        f"/subscriptions/{encoded_id}",
        access_token=get_access_token("onedrive"),
    )


def list_subscriptions() -> list[dict[str, Any]]:
    """Return all Microsoft Graph subscriptions owned by this application."""
    access_token = get_access_token("onedrive")
    response = _get("/subscriptions", access_token=access_token)
    subscriptions = []
    while True:
        value = response.get("value", [])
        if not isinstance(value, list):
            raise GraphRequestError("Microsoft Graph returned malformed subscriptions")
        subscriptions.extend(value)
        next_url = response.get("@odata.nextLink")
        if not next_url:
            return subscriptions
        response = _get_url(next_url, access_token=access_token)


def list_delta_changes(
    folder_id: str,
    *,
    delta_url: str | None = None,
) -> tuple[list[dict[str, Any]], str]:
    """Return all changes since a cursor and the next durable delta URL."""
    if not folder_id.strip():
        raise ValueError("folder_id must not be empty")

    access_token = get_access_token("onedrive")
    encoded_id = quote(folder_id, safe="")
    response = (
        _get_url(delta_url, access_token=access_token)
        if delta_url
        else _get(
            f"/me/drive/items/{encoded_id}/delta?$select={DELTA_FIELDS}",
            access_token=access_token,
        )
    )
    changes_by_id: dict[str, dict[str, Any]] = {}
    while True:
        value = response.get("value", [])
        if not isinstance(value, list):
            raise GraphRequestError("Microsoft Graph returned malformed delta changes")
        for item in value:
            if not isinstance(item, dict):
                raise GraphRequestError("Microsoft Graph returned a malformed delta item")
            item_id = item.get("id")
            if not isinstance(item_id, str) or not item_id:
                raise GraphRequestError("Microsoft Graph returned a delta item without an ID")
            # Graph can repeat an item in one feed and instructs clients to use
            # its last occurrence. Reinsert it so returned order also reflects
            # the last-seen order.
            changes_by_id.pop(item_id, None)
            changes_by_id[item_id] = item

        next_url = response.get("@odata.nextLink")
        if next_url:
            response = _get_url(next_url, access_token=access_token)
            continue

        next_delta_url = response.get("@odata.deltaLink")
        if not isinstance(next_delta_url, str) or not next_delta_url:
            raise GraphRequestError("Microsoft Graph delta response did not include a delta link")
        return list(changes_by_id.values()), next_delta_url
