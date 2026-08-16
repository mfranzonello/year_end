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


def _post(path: str, payload: dict[str, Any], *, access_token: str) -> dict[str, Any]:
    """POST a JSON payload to Microsoft Graph and return its JSON response."""
    request = Request(
        f"{_graph_url()}{path}",
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


def find_folder_id(folder_path: str) -> str:
    """Return the OneDrive item ID for a folder path relative to the drive root."""
    normalized_path = folder_path.strip().strip("/\\")
    if not normalized_path:
        raise ValueError("folder_path must identify a folder below the OneDrive root")

    encoded_path = quote(normalized_path.replace("\\", "/"), safe="/")
    access_token = get_access_token()
    item = _get(
        f"/me/drive/root:/{encoded_path}?$select=id,name,folder",
        access_token=access_token,
    )
    if "folder" not in item:
        raise GraphRequestError(f"The OneDrive path is not a folder: {folder_path!r}")
    item_id = item.get("id")
    if not isinstance(item_id, str) or not item_id:
        raise GraphRequestError(f"Microsoft Graph did not return an ID for folder: {folder_path!r}")
    return item_id


def get_or_create_share_link(
    folder_id: str,
    *,
    link_type: str = "view",
    scope: str = "anonymous",
) -> str:
    """Return an existing folder share URL, or create and return one.

    Any existing sharing-link permission is reused. ``link_type`` and ``scope``
    configure the new link only when the folder does not already have one.
    """
    if not folder_id.strip():
        raise ValueError("folder_id must not be empty")

    access_token = get_access_token()
    encoded_id = quote(folder_id, safe="")
    permissions = _get(
        f"/me/drive/items/{encoded_id}/permissions?$select=link",
        access_token=access_token,
    )
    for permission in permissions.get("value", []):
        web_url = permission.get("link", {}).get("webUrl")
        if isinstance(web_url, str) and web_url:
            return web_url

    permission = _post(
        f"/me/drive/items/{encoded_id}/createLink",
        {"type": link_type, "scope": scope},
        access_token=access_token,
    )
    web_url = permission.get("link", {}).get("webUrl")
    if not isinstance(web_url, str) or not web_url:
        raise GraphRequestError("Microsoft Graph created a sharing permission without returning a URL")
    return web_url


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
