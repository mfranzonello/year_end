"""Manage Google Drive change channels and durable change-page cursors."""

from datetime import datetime, timedelta, timezone
from typing import Any
from urllib.parse import urlparse
from uuid import uuid4

from integrations.google.auth import get_access_token
from integrations.google.google_drive.client import (
    GoogleDriveRequestError, _get, _post, _post_without_response,
)


MAXIMUM_CHANNEL_LIFETIME = timedelta(days=7)
DEFAULT_CHANNEL_LIFETIME = timedelta(days=6, hours=23)
CHANGE_FIELDS = (
    "changes(fileId,removed,time,file(id,name,mimeType,size,parents,trashed,"
    "shortcutDetails(targetId,targetMimeType))),nextPageToken,newStartPageToken"
)


def _utc_datetime(value: datetime) -> datetime:
    """Return an aware UTC datetime or reject an ambiguous timestamp."""
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("Google Drive channel datetimes must include a timezone")
    return value.astimezone(timezone.utc)


def get_start_page_token() -> str:
    """Return a cursor representing the current Google Drive change state."""
    response = _get(
        "/changes/startPageToken",
        {"supportsAllDrives": "true"},
        access_token=get_access_token("google_drive"),
    )
    page_token = response.get("startPageToken")
    if not isinstance(page_token, str) or not page_token:
        raise GoogleDriveRequestError(
            "Google Drive did not return a starting change-page token"
        )
    return page_token


def create_changes_channel(
    notification_url: str,
    channel_token: str,
    *,
    page_token: str | None = None,
    channel_id: str | None = None,
    expires_at: datetime | None = None,
) -> dict[str, Any]:
    """Create a replaceable webhook channel for the user's Drive change log."""
    parsed_url = urlparse(notification_url)
    if parsed_url.scheme.lower() != "https" or not parsed_url.netloc:
        raise ValueError("notification_url must use HTTPS")
    if not channel_token:
        raise ValueError("channel_token must not be empty")

    now = datetime.now(timezone.utc)
    expiration = _utc_datetime(expires_at or now + DEFAULT_CHANNEL_LIFETIME)
    if expiration <= now or expiration > now + MAXIMUM_CHANNEL_LIFETIME:
        raise ValueError("Google Drive channel expiration must be within seven days")

    change_page_token = page_token or get_start_page_token()
    if not change_page_token:
        raise ValueError("page_token must not be empty")
    identifier = channel_id or str(uuid4())
    if not identifier:
        raise ValueError("channel_id must not be empty")

    response = _post(
        "/changes/watch",
        {
            "pageToken": change_page_token,
            "includeItemsFromAllDrives": "true",
            "supportsAllDrives": "true",
        },
        {
            "id": identifier,
            "type": "web_hook",
            "address": notification_url,
            "token": channel_token,
            "expiration": str(int(expiration.timestamp() * 1000)),
        },
        access_token=get_access_token("google_drive"),
    )
    response_id = response.get("id")
    resource_id = response.get("resourceId")
    if response_id != identifier or not isinstance(resource_id, str) or not resource_id:
        raise GoogleDriveRequestError(
            "Google Drive created a malformed notification channel"
        )
    return {**response, "pageToken": change_page_token}


def stop_channel(channel_id: str, resource_id: str) -> None:
    """Stop a superseded Google Drive notification channel."""
    if not channel_id.strip() or not resource_id.strip():
        raise ValueError("channel_id and resource_id must not be empty")
    _post_without_response(
        "/channels/stop",
        {},
        {"id": channel_id, "resourceId": resource_id},
        access_token=get_access_token("google_drive"),
    )


def list_changes(page_token: str) -> tuple[list[dict[str, Any]], str]:
    """Return all changes after a cursor and the next durable start token."""
    if not page_token.strip():
        raise ValueError("page_token must not be empty")

    access_token = get_access_token("google_drive")
    params = {
        "pageToken": page_token,
        "pageSize": "1000",
        "includeItemsFromAllDrives": "true",
        "supportsAllDrives": "true",
        "includeRemoved": "true",
        "spaces": "drive",
        "fields": CHANGE_FIELDS,
    }
    changes_by_id: dict[str, dict[str, Any]] = {}
    while True:
        response = _get("/changes", params, access_token=access_token)
        changes = response.get("changes", [])
        if not isinstance(changes, list):
            raise GoogleDriveRequestError("Google Drive returned malformed changes")
        for change in changes:
            if not isinstance(change, dict):
                raise GoogleDriveRequestError(
                    "Google Drive returned a malformed change entry"
                )
            file_id = change.get("fileId")
            if not isinstance(file_id, str) or not file_id:
                raise GoogleDriveRequestError(
                    "Google Drive returned a change without a file ID"
                )
            changes_by_id.pop(file_id, None)
            changes_by_id[file_id] = change

        next_page_token = response.get("nextPageToken")
        if next_page_token:
            if not isinstance(next_page_token, str):
                raise GoogleDriveRequestError(
                    "Google Drive returned a malformed next-page token"
                )
            params = {**params, "pageToken": next_page_token}
            continue

        new_start_token = response.get("newStartPageToken")
        if not isinstance(new_start_token, str) or not new_start_token:
            raise GoogleDriveRequestError(
                "Google Drive changes did not include a new starting token"
            )
        return list(changes_by_id.values()), new_start_token
