"""Small read-first client for the Microsoft Graph OneDrive endpoints."""

from typing import Any
from urllib.error import HTTPError
from urllib.parse import quote
from urllib.request import Request, urlopen
import base64
import json
import time

from common.config import read_toml
from integrations.microsoft.auth import MicrosoftAuthError, get_access_token


class GraphRequestError(RuntimeError):
    """Raised when Microsoft Graph rejects a request."""


UPLOAD_FRAGMENT_GRANULARITY = 320 * 1024


def _graph_url() -> str:
    """Read the Graph endpoint without loading local-drive configuration."""
    return read_toml("api")["onedrive"]["urls"]["graph"]


def _get(path: str, *, access_token: str) -> dict[str, Any]:
    return _get_url(f"{_graph_url()}{path}", access_token=access_token)


def _get_url(url: str, *, access_token: str) -> dict[str, Any]:
    """GET a configured Graph URL, including an API-provided next page."""
    if not url.startswith(f"{_graph_url()}/"):
        raise GraphRequestError("Microsoft Graph returned an unexpected pagination URL")
    request = Request(
        url,
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


def _patch(path: str, payload: dict[str, Any], *, access_token: str) -> dict[str, Any]:
    """PATCH a JSON payload to Microsoft Graph and return its JSON response."""
    request = Request(
        f"{_graph_url()}{path}",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {access_token}",
            "Accept": "application/json",
            "Content-Type": "application/json",
        },
        method="PATCH",
    )
    try:
        with urlopen(request, timeout=30) as response:
            return json.load(response)
    except HTTPError as error:
        body = error.read().decode("utf-8", errors="replace")
        raise GraphRequestError(f"Microsoft Graph returned HTTP {error.code}: {body}") from error
    except Exception as error:
        raise GraphRequestError(f"Microsoft Graph request failed: {error}") from error


def _delete(path: str, *, access_token: str) -> None:
    """DELETE a Microsoft Graph resource that returns no response body."""
    request = Request(
        f"{_graph_url()}{path}",
        headers={"Authorization": f"Bearer {access_token}", "Accept": "application/json"},
        method="DELETE",
    )
    try:
        with urlopen(request, timeout=30):
            return
    except HTTPError as error:
        body = error.read().decode("utf-8", errors="replace")
        raise GraphRequestError(f"Microsoft Graph returned HTTP {error.code}: {body}") from error
    except Exception as error:
        raise GraphRequestError(f"Microsoft Graph request failed: {error}") from error


def inspect_my_drive(*, force_login: bool = False) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Return root metadata and the first page of root items without changing OneDrive."""
    access_token = get_access_token("onedrive", force_login=force_login)
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
    access_token = get_access_token("onedrive")
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


def list_child_folders(folder_id: str) -> list[dict[str, Any]]:
    """Return the immediate child folders of a OneDrive folder."""
    return [item for item in list_children(folder_id) if "folder" in item]


def _list_children(folder_id: str, access_token: str) -> list[dict[str, Any]]:
    """Return all immediate children using an existing access token."""
    if not folder_id.strip():
        raise ValueError("folder_id must not be empty")

    encoded_id = quote(folder_id, safe="")
    response = _get(
        f"/me/drive/items/{encoded_id}/children?"
        "$select=id,name,webUrl,size,folder,file,video,lastModifiedDateTime&$top=999",
        access_token=access_token,
    )
    children = []
    while True:
        value = response.get("value", [])
        if not isinstance(value, list):
            raise GraphRequestError("Microsoft Graph returned malformed folder children")
        children.extend(value)
        next_url = response.get("@odata.nextLink")
        if not next_url:
            return children
        response = _get_url(next_url, access_token=access_token)


def list_children(folder_id: str) -> list[dict[str, Any]]:
    """Return every immediate file and folder child, following pagination."""
    return _list_children(folder_id, get_access_token("onedrive"))


def list_descendant_files(folder_id: str) -> list[dict[str, Any]]:
    """Return files below a folder with their relative parent folder path."""
    if not folder_id.strip():
        raise ValueError("folder_id must not be empty")

    access_token = get_access_token("onedrive")
    pending = [(folder_id, ())]
    visited = set()
    files = []
    while pending:
        current_id, relative_parts = pending.pop()
        if current_id in visited:
            raise GraphRequestError("Microsoft Graph returned a repeated folder ID")
        visited.add(current_id)
        for item in _list_children(current_id, access_token):
            item_id = item.get("id")
            name = item.get("name")
            if not isinstance(item_id, str) or not item_id:
                raise GraphRequestError("Microsoft Graph returned a child without an ID")
            if not isinstance(name, str) or not name:
                raise GraphRequestError("Microsoft Graph returned a child without a name")
            if "folder" in item:
                pending.append((item_id, (*relative_parts, name)))
            elif "file" in item:
                files.append({**item, "relative_parent": "/".join(relative_parts) or None})
    return files


def create_upload_session(
    folder_id: str,
    file_name: str,
    *,
    conflict_behavior: str = "fail",
) -> dict[str, Any]:
    """Create a resumable upload session beneath an existing OneDrive folder."""
    if not folder_id.strip():
        raise ValueError("folder_id must not be empty")
    if not file_name.strip() or "/" in file_name or "\\" in file_name:
        raise ValueError("file_name must be a non-empty leaf filename")
    if conflict_behavior not in {"fail", "replace", "rename"}:
        raise ValueError("conflict_behavior must be fail, replace, or rename")

    encoded_id = quote(folder_id, safe="")
    encoded_name = quote(file_name, safe="")
    session = _post(
        f"/me/drive/items/{encoded_id}:/{encoded_name}:/createUploadSession",
        {
            "item": {
                "@microsoft.graph.conflictBehavior": conflict_behavior,
                "name": file_name,
            },
        },
        access_token=get_access_token("onedrive"),
    )
    upload_url = session.get("uploadUrl")
    if not isinstance(upload_url, str) or not upload_url.startswith("https://"):
        raise GraphRequestError(
            "Microsoft Graph created an upload session without a secure upload URL"
        )
    return session


def upload_chunk(upload_url: str, content: bytes, start: int, total: int) -> dict[str, Any]:
    """Upload one sequential fragment to an existing OneDrive upload session."""
    if not upload_url.startswith("https://"):
        raise ValueError("upload_url must be a secure URL returned by Microsoft Graph")
    if not content:
        raise ValueError("content must not be empty")
    if start < 0 or total <= 0 or start + len(content) > total:
        raise ValueError("content range must fit within the declared file size")
    if start % UPLOAD_FRAGMENT_GRANULARITY:
        raise ValueError("upload chunk offsets must be a multiple of 320 KiB")
    if start + len(content) < total and len(content) % UPLOAD_FRAGMENT_GRANULARITY:
        raise ValueError("non-final upload chunks must be a multiple of 320 KiB")

    end = start + len(content) - 1
    request = Request(
        upload_url,
        data=content,
        headers={
            "Content-Length": str(len(content)),
            "Content-Range": f"bytes {start}-{end}/{total}",
            "Content-Type": "application/octet-stream",
        },
        method="PUT",
    )
    try:
        with urlopen(request, timeout=120) as response:
            status = getattr(response, "status", response.getcode())
            if status not in {200, 201, 202}:
                raise GraphRequestError(
                    f"OneDrive upload returned unexpected HTTP {status}"
                )
            return json.load(response)
    except HTTPError as error:
        body = error.read().decode("utf-8", errors="replace")
        raise GraphRequestError(
            f"OneDrive upload returned HTTP {error.code}: {body}"
        ) from error
    except GraphRequestError:
        raise
    except Exception as error:
        raise GraphRequestError(f"OneDrive upload failed: {error}") from error


def get_upload_session_status(upload_url: str) -> dict[str, Any]:
    """Return expiration and expected ranges for an active upload session."""
    if not upload_url.startswith("https://"):
        raise ValueError("upload_url must be a secure URL returned by Microsoft Graph")
    request = Request(upload_url, headers={"Accept": "application/json"})
    try:
        with urlopen(request, timeout=30) as response:
            return json.load(response)
    except HTTPError as error:
        body = error.read().decode("utf-8", errors="replace")
        raise GraphRequestError(
            f"OneDrive upload status returned HTTP {error.code}: {body}"
        ) from error
    except Exception as error:
        raise GraphRequestError(f"OneDrive upload status failed: {error}") from error


def cancel_upload_session(upload_url: str) -> None:
    """Cancel an incomplete OneDrive upload session without Graph authentication."""
    if not upload_url.startswith("https://"):
        raise ValueError("upload_url must be a secure URL returned by Microsoft Graph")
    request = Request(upload_url, method="DELETE")
    try:
        with urlopen(request, timeout=30):
            return
    except HTTPError as error:
        body = error.read().decode("utf-8", errors="replace")
        raise GraphRequestError(
            f"OneDrive upload cancellation returned HTTP {error.code}: {body}"
        ) from error
    except Exception as error:
        raise GraphRequestError(
            f"OneDrive upload cancellation failed: {error}"
        ) from error


def get_share_link(
    folder_id: str,
    *,
    link_type: str = "edit",
    scope: str = "anonymous",
) -> str | None:
    """Return a matching existing folder share URL without creating one."""
    if not folder_id.strip():
        raise ValueError("folder_id must not be empty")

    access_token = get_access_token("onedrive")
    encoded_id = quote(folder_id, safe="")
    permissions = _get(
        f"/me/drive/items/{encoded_id}/permissions?$select=link,inheritedFrom",
        access_token=access_token,
    )
    for permission in permissions.get("value", []):
        link = permission.get("link", {})
        web_url = link.get("webUrl")
        if (
            not permission.get("inheritedFrom")
            and link.get("type") == link_type
            and link.get("scope") == scope
            and isinstance(web_url, str)
            and web_url
        ):
            return web_url
    return None


def get_or_create_share_link(
    folder_id: str,
    *,
    link_type: str = "edit",
    scope: str = "anonymous",
) -> str:
    """Return a matching folder share URL, creating it when absent."""
    if web_url := get_share_link(folder_id, link_type=link_type, scope=scope):
        return web_url

    access_token = get_access_token("onedrive")
    encoded_id = quote(folder_id, safe="")
    for attempt in range(3):
        try:
            permission = _post(
                f"/me/drive/items/{encoded_id}/createLink",
                {"type": link_type, "scope": scope},
                access_token=access_token,
            )
            break
        except GraphRequestError as error:
            if "sharingFailed" not in str(error) or attempt == 2:
                raise
            time.sleep(2 ** attempt)
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
    access_token = get_access_token("onedrive")
    sharing_token = quote(encode_sharing_url(sharing_url), safe="!")
    return _get(
        f"/shares/{sharing_token}/driveItem?$expand=children($select=id,name,webUrl,size,folder,file)",
        access_token=access_token,
    )
