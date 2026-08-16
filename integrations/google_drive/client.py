"""Read-first Google Drive API client."""

from typing import Any
from urllib.error import HTTPError
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen
import json

from common.config import read_toml
from integrations.google.auth import get_access_token


class GoogleDriveRequestError(RuntimeError):
    """Raised when the Google Drive API rejects a request."""


FOLDER_MIME_TYPE = "application/vnd.google-apps.folder"


def _api_url() -> str:
    """Return the configured Google Drive API base URL."""
    return read_toml("api")["google_drive"]["urls"]["api"]


def _get(path: str, params: dict[str, str], *, access_token: str) -> dict[str, Any]:
    request = Request(
        f"{_api_url()}{path}?{urlencode(params)}",
        headers={"Authorization": f"Bearer {access_token}", "Accept": "application/json"},
    )
    try:
        with urlopen(request, timeout=30) as response:
            return json.load(response)
    except HTTPError as error:
        body = error.read().decode("utf-8", errors="replace")
        raise GoogleDriveRequestError(f"Google Drive API returned HTTP {error.code}: {body}") from error
    except Exception as error:
        raise GoogleDriveRequestError(f"Google Drive API request failed: {error}") from error


def _post(
    path: str,
    params: dict[str, str],
    payload: dict[str, Any],
    *,
    access_token: str,
) -> dict[str, Any]:
    """POST a JSON payload to Google Drive and return its JSON response."""
    request = Request(
        f"{_api_url()}{path}?{urlencode(params)}",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {access_token}",
            "Accept": "application/json",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urlopen(request, timeout=30) as response:
            return json.load(response)
    except HTTPError as error:
        body = error.read().decode("utf-8", errors="replace")
        raise GoogleDriveRequestError(f"Google Drive API returned HTTP {error.code}: {body}") from error
    except Exception as error:
        raise GoogleDriveRequestError(f"Google Drive API request failed: {error}") from error


def _escape_query_value(value: str) -> str:
    """Escape a string literal for the Google Drive ``q`` query language."""
    return value.replace("\\", "\\\\").replace("'", "\\'")


def list_root_items(*, force_login: bool = False) -> list[dict[str, Any]]:
    """List the first page of root-level Drive items without changing Drive."""
    return _get("/files", {
        "q": "'root' in parents and trashed = false",
        "pageSize": "100",
        "orderBy": "folder,name",
        "fields": "files(id,name,mimeType,webViewLink,modifiedTime,size,parents),nextPageToken",
        "spaces": "drive",
    }, access_token=get_access_token("google_drive", force_login=force_login)).get("files", [])


def find_folder_id(folder_path: str) -> str:
    """Return the Google Drive ID for a folder path relative to My Drive."""
    normalized_path = folder_path.strip().strip("/\\")
    if not normalized_path:
        raise ValueError("folder_path must identify a folder below the Google Drive root")

    access_token = get_access_token("google_drive")
    parent_id = "root"
    for folder_name in normalized_path.replace("\\", "/").split("/"):
        if not folder_name:
            raise ValueError(f"folder_path contains an empty path segment: {folder_path!r}")
        escaped_name = _escape_query_value(folder_name)
        escaped_parent = _escape_query_value(parent_id)
        response = _get("/files", {
            "q": (
                f"name = '{escaped_name}' and '{escaped_parent}' in parents and "
                f"mimeType = '{FOLDER_MIME_TYPE}' and trashed = false"
            ),
            "pageSize": "2",
            "fields": "files(id,name)",
            "spaces": "drive",
        }, access_token=access_token)
        matches = response.get("files", [])
        if not matches:
            raise GoogleDriveRequestError(f"Google Drive folder was not found: {folder_path!r}")
        if len(matches) > 1:
            raise GoogleDriveRequestError(
                f"Google Drive path is ambiguous because its parent contains duplicate folders named {folder_name!r}"
            )
        item_id = matches[0].get("id")
        if not isinstance(item_id, str) or not item_id:
            raise GoogleDriveRequestError(f"Google Drive did not return an ID for folder: {folder_path!r}")
        parent_id = item_id
    return parent_id


def get_or_create_share_link(folder_id: str) -> str:
    """Ensure a folder has an anyone-with-link reader permission and return its URL."""
    if not folder_id.strip():
        raise ValueError("folder_id must not be empty")

    access_token = get_access_token("google_drive")
    encoded_id = quote(folder_id, safe="")
    folder = _get(
        f"/files/{encoded_id}",
        {"fields": "id,mimeType,webViewLink"},
        access_token=access_token,
    )
    if folder.get("mimeType") != FOLDER_MIME_TYPE:
        raise GoogleDriveRequestError(f"The Google Drive item is not a folder: {folder_id!r}")
    web_url = folder.get("webViewLink")
    if not isinstance(web_url, str) or not web_url:
        raise GoogleDriveRequestError("Google Drive did not return a web URL for the folder")

    permissions = _get(
        f"/files/{encoded_id}/permissions",
        {"fields": "permissions(id,type,role)", "pageSize": "100"},
        access_token=access_token,
    )
    if not any(permission.get("type") == "anyone" for permission in permissions.get("permissions", [])):
        _post(
            f"/files/{encoded_id}/permissions",
            {"fields": "id,type,role"},
            {"type": "anyone", "role": "reader"},
            access_token=access_token,
        )
    return web_url
