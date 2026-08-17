"""Google Calendar API client for project-owned recurring events."""

from typing import Any
from datetime import datetime
from urllib.error import HTTPError
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen
import json
from time import sleep

from common.config import read_toml
from integrations.google.auth import get_access_token


MANAGED_PROPERTY = "yearEndManaged"
MANAGED_VALUE = "true"


class GoogleCalendarRequestError(RuntimeError):
    """Raised when the Google Calendar API rejects a request."""


def _api_url() -> str:
    """Return the configured Google Calendar API base URL."""
    return read_toml("api")["google_calendar"]["urls"]["api"]


def _request(
    method: str,
    path: str,
    *,
    access_token: str,
    params: dict[str, str] | None = None,
    payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Make one authenticated Calendar API request."""
    query = f"?{urlencode(params)}" if params else ""
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    for attempt in range(3):
        request = Request(
            f"{_api_url()}{path}{query}",
            data=data,
            headers={
                "Authorization": f"Bearer {access_token}",
                "Accept": "application/json",
                **({"Content-Type": "application/json"} if data is not None else {}),
            },
            method=method,
        )
        try:
            with urlopen(request, timeout=30) as response:
                return json.load(response)
        except HTTPError as error:
            body = error.read().decode("utf-8", errors="replace")
            raise GoogleCalendarRequestError(
                f"Google Calendar API returned HTTP {error.code}: {body}"
            ) from error
        except OSError as error:
            if attempt < 2:
                sleep(attempt + 1)
                continue
            raise GoogleCalendarRequestError(
                f"Google Calendar API request failed after 3 attempts: {error}"
            ) from error
        except Exception as error:
            raise GoogleCalendarRequestError(
                f"Google Calendar API request failed: {error}"
            ) from error
    raise AssertionError("Calendar request retry loop exited unexpectedly")


def list_managed_events(
    calendar_id: str,
    *,
    force_login: bool = False,
) -> list[dict[str, Any]]:
    """Return recurring event masters owned by this project."""
    if not calendar_id.strip():
        raise ValueError("calendar_id must not be empty")

    access_token = get_access_token("google_calendar", force_login=force_login)
    path = f"/calendars/{quote(calendar_id, safe='')}/events"
    params = {
        "privateExtendedProperty": f"{MANAGED_PROPERTY}={MANAGED_VALUE}",
        "showDeleted": "false",
        "singleEvents": "false",
        "maxResults": "2500",
    }
    events = []
    while True:
        response = _request("GET", path, access_token=access_token, params=params)
        events.extend(
            event
            for event in response.get("items", [])
            if not event.get("recurringEventId")
        )
        page_token = response.get("nextPageToken")
        if not page_token:
            return events
        params = {**params, "pageToken": page_token}


def list_event_instances(
    calendar_id: str,
    time_min: datetime,
    time_max: datetime,
) -> list[dict[str, Any]]:
    """Return expanded event instances in a bounded half-open time window."""
    if not calendar_id.strip():
        raise ValueError("calendar_id must not be empty")
    if time_min.tzinfo is None or time_max.tzinfo is None:
        raise ValueError("time_min and time_max must be timezone-aware")
    if time_min >= time_max:
        raise ValueError("time_min must be before time_max")

    access_token = get_access_token("google_calendar")
    path = f"/calendars/{quote(calendar_id, safe='')}/events"
    params = {
        "timeMin": time_min.isoformat(),
        "timeMax": time_max.isoformat(),
        "showDeleted": "false",
        "singleEvents": "true",
        "orderBy": "startTime",
        "maxResults": "2500",
    }
    events = []
    while True:
        response = _request("GET", path, access_token=access_token, params=params)
        events.extend(response.get("items", []))
        page_token = response.get("nextPageToken")
        if not page_token:
            return events
        params = {**params, "pageToken": page_token}


def get_event(calendar_id: str, event_id: str) -> dict[str, Any]:
    """Return one recurring master or ordinary event without changing it."""
    if not calendar_id.strip() or not event_id.strip():
        raise ValueError("calendar_id and event_id must not be empty")
    return _request(
        "GET",
        (
            f"/calendars/{quote(calendar_id, safe='')}/events/"
            f"{quote(event_id, safe='')}"
        ),
        access_token=get_access_token("google_calendar"),
    )


def create_event(calendar_id: str, event: dict[str, Any]) -> dict[str, Any]:
    """Create one explicitly supplied managed event."""
    if not calendar_id.strip():
        raise ValueError("calendar_id must not be empty")
    return _request(
        "POST",
        f"/calendars/{quote(calendar_id, safe='')}/events",
        access_token=get_access_token("google_calendar"),
        payload=event,
    )


def update_event(
    calendar_id: str,
    event_id: str,
    event: dict[str, Any],
) -> dict[str, Any]:
    """Patch one project-owned event without changing unrelated fields."""
    if not calendar_id.strip() or not event_id.strip():
        raise ValueError("calendar_id and event_id must not be empty")
    return _request(
        "PATCH",
        (
            f"/calendars/{quote(calendar_id, safe='')}/events/"
            f"{quote(event_id, safe='')}"
        ),
        access_token=get_access_token("google_calendar"),
        payload=event,
    )
