"""Read-first Google Drive API client."""

from typing import Any
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import Request, urlopen
import json

from common.config import read_toml
from integrations.google_drive.auth import get_access_token


class GoogleDriveRequestError(RuntimeError):
    """Raised when the Google Drive API rejects a request."""


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


def list_root_items(*, force_login: bool = False) -> list[dict[str, Any]]:
    """List the first page of root-level Drive items without changing Drive."""
    return _get("/files", {
        "q": "'root' in parents and trashed = false",
        "pageSize": "100",
        "orderBy": "folder,name",
        "fields": "files(id,name,mimeType,webViewLink,modifiedTime,size,parents),nextPageToken",
        "spaces": "drive",
    }, access_token=get_access_token(force_login=force_login)).get("files", [])
