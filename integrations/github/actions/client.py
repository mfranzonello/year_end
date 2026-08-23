"""Dispatch repository events that select cloud media workflows."""

from typing import Any
from urllib.error import HTTPError
from urllib.parse import quote
from urllib.request import Request, urlopen
import json

from common.config import read_toml
from integrations.github.auth import get_installation_token


class GitHubDispatchError(RuntimeError):
    """Raised when GitHub rejects an automation workflow dispatch."""


def _api_url() -> str:
    """Return the configured GitHub REST API base URL."""
    return read_toml("api")["github"]["urls"]["api"].rstrip("/")


def dispatch_repository_event(
    repository: str,
    event_type: str,
    *,
    app_id: str,
    installation_id: str,
    private_key: str,
    client_payload: dict[str, Any] | None = None,
) -> None:
    """Dispatch one validated event to a repository's matching workflow."""
    repository_parts = repository.strip().split("/")
    if len(repository_parts) != 2 or not all(repository_parts):
        raise ValueError("repository must use owner/name format")
    if not event_type.strip() or len(event_type) > 100:
        raise ValueError("event_type must contain between 1 and 100 characters")

    owner, name = (quote(part, safe="") for part in repository_parts)
    token = get_installation_token(app_id, installation_id, private_key)
    body = json.dumps({
        "event_type": event_type,
        "client_payload": client_payload or {},
    }).encode("utf-8")
    request = Request(
        f"{_api_url()}/repos/{owner}/{name}/dispatches",
        data=body,
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "Content-Type": "application/json",
            "User-Agent": "year-end-automation",
            "X-GitHub-Api-Version": "2022-11-28",
        },
        method="POST",
    )
    try:
        with urlopen(request, timeout=30) as response:
            status = getattr(response, "status", response.getcode())
            if status != 204:
                raise GitHubDispatchError(
                    f"GitHub repository dispatch returned unexpected HTTP {status}"
                )
    except HTTPError as error:
        body_text = error.read().decode("utf-8", errors="replace")
        raise GitHubDispatchError(
            f"GitHub repository dispatch returned HTTP {error.code}: {body_text}"
        ) from error
    except GitHubDispatchError:
        raise
    except Exception as error:
        raise GitHubDispatchError(f"GitHub repository dispatch failed: {error}") from error
