"""Unit tests for the Google Calendar API client."""

from unittest import TestCase
from unittest.mock import patch

from integrations.google.google_calendar.client import (
    create_event,
    get_calendar,
    list_managed_events,
    update_event,
)


class GoogleCalendarClientTests(TestCase):
    @patch("integrations.google.google_calendar.client.get_access_token", return_value="token")
    @patch("integrations.google.google_calendar.client._request")
    def test_gets_configured_calendar(self, request, get_token):
        request.return_value = {"id": "calendar-id", "summary": "Family"}

        result = get_calendar("calendar-id", force_login=True)

        self.assertEqual(result["summary"], "Family")
        get_token.assert_called_once_with("google_calendar", force_login=True)
        self.assertEqual(request.call_args.args, ("GET", "/calendars/calendar-id"))

    @patch("integrations.google.google_calendar.client.get_access_token", return_value="token")
    @patch("integrations.google.google_calendar.client._request")
    def test_lists_all_managed_event_pages(self, request, _get_token):
        request.side_effect = [
            {"items": [{"id": "first"}], "nextPageToken": "next"},
            {"items": [{"id": "second"}]},
        ]

        events = list_managed_events("calendar/id")

        self.assertEqual([event["id"] for event in events], ["first", "second"])
        self.assertEqual(request.call_count, 2)
        first_params = request.call_args_list[0].kwargs["params"]
        second_params = request.call_args_list[1].kwargs["params"]
        self.assertEqual(first_params["privateExtendedProperty"], "yearEndManaged=true")
        self.assertEqual(second_params["pageToken"], "next")

    @patch("integrations.google.google_calendar.client.get_access_token", return_value="token")
    @patch("integrations.google.google_calendar.client._request")
    def test_creates_and_updates_events(self, request, _get_token):
        request.side_effect = [{"id": "created"}, {"id": "updated"}]
        payload = {"summary": "Birthday"}

        created = create_event("calendar-id", payload)
        updated = update_event("calendar-id", "event/id", payload)

        self.assertEqual(created["id"], "created")
        self.assertEqual(updated["id"], "updated")
        self.assertEqual(request.call_args_list[0].args[0], "POST")
        self.assertEqual(request.call_args_list[1].args[0], "PATCH")
        self.assertIn("event%2Fid", request.call_args_list[1].args[1])
