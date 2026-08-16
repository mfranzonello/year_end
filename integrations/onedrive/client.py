"""Small read-first client for the Microsoft Graph OneDrive endpoints."""

from typing import Any
from urllib.error import HTTPError
from urllib.parse import quote
from urllib.request import Request, urlopen
import base64
import json

from common.config import read_toml
from integrations.onedrive.auth import MicrosoftAuthError, get_access_token


class GraphRequestError(RuntimeError):
    """Raised when Microsoft Graph rejects a request."""


def _graph_url() -> str:
    """Read the Graph endpoint without loading local-drive configuration."""
    return read_toml("api")["onedrive"]["urls"]["graph"]


def _get(path: str, *, access_token: str) -> dict[str, Any]:
    request = Request(
        f"{_graph_url()}{path}",
        headers={"Authorization": f"Bearer {access_token}", "Accept": "application/json"},
    )
    try:
        with urlopen(request, timeout=30) as response:
            return json.load(response)
    except HTTPError as error:
        body = error.read().decode("utf-8", errors="replace")
        raise GraphRequestError(f"Microsoft Graph returned HTTP {error.code}: {body}") from error
    except Exception as error:
        raise GraphRequestError(f"Microsoft Graph request failed: {error}") from error


def inspect_my_drive(*, force_login: bool = False) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Return root metadata and the first page of root items without changing OneDrive."""
    access_token = get_access_token(force_login=force_login)
    root = _get("/me/drive/root?$select=id,name,webUrl,folder", access_token=access_token)
    children = _get(
        "/me/drive/root/children?$select=id,name,webUrl,size,folder,file,lastModifiedDateTime&$top=200",
        access_token=access_token,
    )
    return root, children.get("value", [])


def encode_sharing_url(sharing_url: str) -> str:
    """Convert a sharing URL to the `u!` token Microsoft Graph expects."""
    encoded = base64.urlsafe_b64encode(sharing_url.encode("utf-8")).decode("ascii").rstrip("=")
    return f"u!{encoded}"


def resolve_shared_folder(sharing_url: str) -> dict[str, Any]:
    """Resolve a shared OneDrive URL to its canonical drive item (read-only)."""
    access_token = get_access_token()
    sharing_token = quote(encode_sharing_url(sharing_url), safe="!")
    return _get(
        f"/shares/{sharing_token}/driveItem?$expand=children($select=id,name,webUrl,size,folder,file)",
        access_token=access_token,
    )
