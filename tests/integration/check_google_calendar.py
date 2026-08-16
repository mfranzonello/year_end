"""Authorize Calendar event access and inspect the configured shared calendar."""

import argparse

from common.secret import secrets
from integrations.google.auth import GoogleAuthError
from integrations.google.google_calendar.client import (
    GoogleCalendarRequestError,
    get_calendar,
    list_managed_events,
)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Authorize Google Calendar and inspect managed events without changes."
    )
    parser.add_argument(
        "--login",
        action="store_true",
        help="Ignore cached Calendar credentials and show consent again.",
    )
    args = parser.parse_args()
    calendar_id = secrets["google_calendar"]["calendar_id"]
    try:
        calendar = get_calendar(calendar_id, force_login=args.login)
        managed_events = list_managed_events(calendar_id)
    except (GoogleAuthError, GoogleCalendarRequestError) as error:
        raise SystemExit(f"Google Calendar check failed: {error}") from error
    print(
        f"Connected to {calendar.get('summary', 'configured calendar')}. "
        f"Found {len(managed_events)} project-managed event(s)."
    )


if __name__ == "__main__":
    main()
