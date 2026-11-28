import importlib
import sys
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import Mock, patch

from streamlit.testing.v1 import AppTest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
appointments = importlib.import_module("views.appointments")
notifications = importlib.import_module("views.notifications")


class NotificationArchiveTests(unittest.TestCase):
    def test_mark_all_read_clears_streamlit_data_cache(self):
        connection = Mock()
        with (
            patch.object(
                notifications,
                "get_local_connection",
                return_value=connection,
            ),
            patch.object(
                notifications.st.cache_data,
                "clear",
            ) as clear_all,
        ):
            notifications._mark_notifications_read(
                {"appointment:17"},
                invalidate_cache=True,
            )

        connection.executemany.assert_called_once()
        connection.commit.assert_called_once_with()
        clear_all.assert_called_once_with()

    def test_notification_reads_cache_for_twenty_seconds_and_can_be_cleared(self):
        notifications._clear_notification_cache()
        client = Mock()
        query = Mock()
        query.select.return_value = query
        query.order.return_value = query
        query.limit.return_value = query
        query.execute.return_value = Mock(
            data=[{"appointment_id": 17, "patient_name": "Example"}]
        )
        client.table.return_value = query

        try:
            first = notifications._load_notification_table(
                client, "appointments"
            )
            second = notifications._load_notification_table(
                client, "appointments"
            )

            self.assertEqual(first, second)
            self.assertEqual(client.table.call_count, 1)

            appointments._invalidate_schedule_data_caches()
            notifications._load_notification_table(client, "appointments")
            self.assertEqual(client.table.call_count, 2)
        finally:
            notifications._clear_notification_cache()

    def test_clear_control_resets_search_and_requested_date(self):
        app = AppTest.from_string(
            "\n".join(
                [
                    "import streamlit as st",
                    "from views.notifications import _clear_notification_filters",
                    "st.selectbox('Date applies to', ['Requested Date', 'Date Sent (Received)'], key='notification-date-field')",
                    "st.date_input('Requested date', value=st.session_state.get('notification-requested-date-filter-value'), key='notification-requested-date-filter')",
                    "st.selectbox('Sort / Order', ['Newest Sent First', 'Oldest Sent First', 'Soonest Requested Date'], key='notification-sort-order')",
                    "st.text_input('Search requests', key='notification-request-search')",
                    "st.button('✕', key='clear-filters', help='Clear search', on_click=_clear_notification_filters)",
                ]
            )
        )
        app.session_state["notification-requested-date-filter"] = date(2026, 3, 2)
        app.session_state["notification-requested-date-filter-value"] = date(
            2026, 3, 2
        )
        app.session_state["notification-date-field"] = "Date Sent (Received)"
        app.session_state["notification-sort-order"] = "Soonest Requested Date"
        app.session_state["notification-request-search"] = "Jordan"
        app.run()

        app.button(key="clear-filters").click().run()

        self.assertIsNone(app.session_state["notification-requested-date-filter"])
        self.assertIsNone(
            app.session_state["notification-requested-date-filter-value"]
        )
        self.assertEqual(app.session_state["notification-request-search"], "")
        self.assertEqual(
            app.session_state["notification-date-field"],
            "Requested Date",
        )
        self.assertEqual(
            app.session_state["notification-sort-order"],
            "Newest Sent First",
        )

    def test_partitions_requests_and_enforces_archive_retention(self):
        today = date(2026, 3, 2)
        items = [
            {
                "id": "future-pending",
                "status": "Pending",
                "requested_date": "2026-03-03",
            },
            {
                "id": "missing-date",
                "status": "Awaiting",
                "requested_date": None,
            },
            {
                "id": "archive-boundary",
                "status": "unresponded",
                "requested_date": "2026-02-15",
            },
            {
                "id": "expired-pending",
                "status": "Pending",
                "requested_date": "2026-02-14",
            },
            {
                "id": "old-confirmed",
                "status": "Confirmed",
                "requested_date": "2025-01-01",
            },
            {
                "id": "recent-cancelled",
                "status": "Cancelled",
                "requested_date": "2025-01-01",
                "updated_at": "2026-03-01T17:00:00Z",
            },
            {
                "id": "expired-declined",
                "status": "declined",
                "requested_date": "2026-03-02",
                "updated_at": "2026-02-14T16:00:00+08:00",
            },
        ]

        not_responded, responded, archived = (
            notifications._partition_notification_items(items, today)
        )

        self.assertEqual(
            {item["id"] for item in not_responded},
            {"future-pending", "missing-date"},
        )
        self.assertEqual({item["id"] for item in responded}, {"old-confirmed"})
        self.assertEqual(
            {item["id"] for item in archived},
            {"archive-boundary", "recent-cancelled"},
        )

    def test_date_filter_only_matches_requested_date(self):
        items = [
            {"id": "match", "requested_date": "2026-03-02"},
            {"id": "other", "requested_date": "2026-03-03"},
            {"id": "invalid", "requested_date": None},
        ]

        self.assertEqual(
            [
                item["id"]
                for item in notifications._filter_notification_items_by_date(
                    items, date(2026, 3, 2)
                )
            ],
            ["match"],
        )
        self.assertIs(
            notifications._filter_notification_items_by_date(items, None),
            items,
        )

    def test_date_filter_can_match_received_timestamp_in_manila_time(self):
        items = [
            {"id": "sent", "created_at": "2026-03-01T16:30:00Z"},
            {"id": "other", "created_at": "2026-03-02T16:30:00Z"},
            {"id": "invalid", "created_at": None},
        ]

        self.assertEqual(
            [
                item["id"]
                for item in notifications._filter_notification_items_by_date_field(
                    items,
                    date(2026, 3, 2),
                    "Date Sent (Received)",
                )
            ],
            ["sent"],
        )

    def test_notification_sort_orders_use_received_and_requested_schedule(self):
        items = [
            {
                "id": "later-sent",
                "created_at": "2026-03-02T10:00:00+08:00",
                "requested_date": "2026-03-05",
                "requested_time": "09:00:00",
            },
            {
                "id": "earlier-sent",
                "created_at": "2026-03-01T10:00:00+08:00",
                "requested_date": "2026-03-04",
                "requested_time": "10:00:00",
            },
            {
                "id": "same-day-earlier-time",
                "created_at": None,
                "requested_date": "2026-03-04",
                "requested_time": "08:00:00",
            },
        ]

        self.assertEqual(
            [
                item["id"]
                for item in notifications._sort_notification_items(
                    items,
                    "Newest Sent First",
                )
            ],
            ["later-sent", "earlier-sent", "same-day-earlier-time"],
        )
        self.assertEqual(
            [
                item["id"]
                for item in notifications._sort_notification_items(
                    items,
                    "Oldest Sent First",
                )
            ],
            ["earlier-sent", "later-sent", "same-day-earlier-time"],
        )
        self.assertEqual(
            [
                item["id"]
                for item in notifications._sort_notification_items(
                    items,
                    "Soonest Requested Date",
                )
            ],
            ["same-day-earlier-time", "earlier-sent", "later-sent"],
        )

    def test_search_matches_patient_name_and_contact_case_insensitively(self):
        items = [
            {
                "id": "name-match",
                "title": "Jordan Smith",
                "contact": "0912-345-6789",
            },
            {
                "id": "contact-match",
                "title": "Alex Patient",
                "contact": "555-0123",
            },
            {
                "id": "other",
                "title": "Sam Patient",
                "contact": "555-9876",
            },
        ]

        self.assertEqual(
            [
                item["id"]
                for item in notifications._filter_notification_items_by_search(
                    items, "jOrDaN"
                )
            ],
            ["name-match"],
        )
        self.assertEqual(
            [
                item["id"]
                for item in notifications._filter_notification_items_by_search(
                    items, "555-0123"
                )
            ],
            ["contact-match"],
        )

    def test_archived_requests_are_grouped_and_sorted_by_activity(self):
        items = [
            {
                "id": "past-recent-date",
                "status": "Pending",
                "requested_date": "2026-03-01",
                "updated_at": "2026-02-28T12:00:00Z",
            },
            {
                "id": "past-recent-activity",
                "status": "Awaiting",
                "requested_date": "2026-02-28",
                "updated_at": "2026-03-01T12:00:00Z",
            },
            {
                "id": "cancelled-older",
                "status": "Cancelled",
                "updated_at": "2026-03-01T10:00:00Z",
            },
            {
                "id": "declined-newer",
                "status": "Declined",
                "updated_at": "2026-03-01T12:00:00Z",
            },
            {
                "id": "today-pending",
                "status": "Pending",
                "requested_date": "2026-03-02",
            },
        ]

        past_unanswered, cancelled_requests = (
            notifications._partition_archived_notification_items(
                items,
                today=date(2026, 3, 2),
            )
        )

        self.assertEqual(
            [item["id"] for item in past_unanswered],
            ["past-recent-activity", "past-recent-date"],
        )
        self.assertEqual(
            [item["id"] for item in cancelled_requests],
            ["declined-newer", "cancelled-older"],
        )

    def test_latest_activity_sort_key_prefers_updates_then_created_and_id(self):
        items = [
            {
                "request_id": "updated",
                "created_at": "2026-01-01T00:00:00Z",
                "updated_at": "2026-03-02T00:00:00Z",
            },
            {
                "request_id": "new",
                "created_at": "2026-03-01T00:00:00Z",
                "updated_at": None,
            },
            {
                "request_id": "tie-a",
                "created_at": "2026-02-28T00:00:00Z",
                "updated_at": "2026-03-01T00:00:00Z",
            },
            {
                "request_id": "tie-z",
                "created_at": "2026-02-28T00:00:00Z",
                "updated_at": "2026-03-01T00:00:00Z",
            },
        ]

        items.sort(
            key=appointments._latest_activity_sort_key,
            reverse=True,
        )

        self.assertEqual(
            [item["request_id"] for item in items],
            ["updated", "new", "tie-z", "tie-a"],
        )


if __name__ == "__main__":
    unittest.main()
