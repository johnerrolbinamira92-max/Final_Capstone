import datetime
import importlib
import sys
from pathlib import Path
import unittest

from streamlit.testing.v1 import AppTest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
dashboard = importlib.import_module("views.dashboard")


class _Response:
    def __init__(self, count):
        self.count = count


class _Query:
    def __init__(self, events):
        self.events = events
        self.choice_type = None
        self.start = None
        self.end = None

    def select(self, *_args, **_kwargs):
        return self

    def eq(self, _column, value):
        self.choice_type = value
        return self

    def gte(self, _column, value):
        self.start = datetime.datetime.fromisoformat(value)
        return self

    def lte(self, _column, value):
        self.end = datetime.datetime.fromisoformat(value)
        return self

    def execute(self):
        count = sum(
            1
            for event_type, created_at in self.events
            if event_type == self.choice_type
            and (self.start is None or created_at >= self.start)
            and (self.end is None or created_at <= self.end)
        )
        return _Response(count)


class _Client:
    def __init__(self, events):
        self.events = events
        self.tables = []

    def table(self, table_name):
        self.tables.append(table_name)
        return _Query(self.events)


class _HelpRequestQuery:
    def __init__(self, rows):
        self.rows = rows
        self.start = None
        self.end = None

    def select(self, _column, *, count, head):
        if count != "exact" or not head:
            raise AssertionError("Expected an exact-count head query.")
        return self

    def gte(self, _column, value):
        self.start = datetime.datetime.fromisoformat(value)
        return self

    def lte(self, _column, value):
        self.end = datetime.datetime.fromisoformat(value)
        return self

    def execute(self):
        count = sum(
            1
            for row in self.rows
            if (
                self.start is None
                or datetime.datetime.fromisoformat(row["created_at"])
                >= self.start
            )
            and datetime.datetime.fromisoformat(row["created_at"]) <= self.end
        )
        return _Response(count)


class _HelpRequestClient:
    def __init__(self, rows):
        self.rows = rows
        self.tables = []

    def table(self, table_name):
        self.tables.append(table_name)
        if table_name != "patient_help_requests":
            raise AssertionError("Help request counts must use the request table.")
        return _HelpRequestQuery(self.rows)


class PortalEngagementTests(unittest.TestCase):
    def setUp(self):
        self.now = datetime.datetime(
            2026,
            11,
            28,
            11,
            30,
            tzinfo=dashboard.PORTAL_ENGAGEMENT_TIMEZONE,
        )

    def test_time_windows_use_philippine_local_time(self):
        daily_start, daily_end = dashboard._portal_engagement_time_window(
            "Daily",
            self.now,
        )
        weekly_start, _ = dashboard._portal_engagement_time_window(
            "Weekly",
            self.now,
        )
        monthly_start, _ = dashboard._portal_engagement_time_window(
            "Monthly",
            self.now,
        )
        yearly_start, _ = dashboard._portal_engagement_time_window(
            "Yearly",
            self.now,
        )
        all_time_start, _ = dashboard._portal_engagement_time_window(
            "All Time",
            self.now,
        )

        self.assertEqual(
            daily_start,
            datetime.datetime(
                2026,
                11,
                27,
                16,
                0,
                tzinfo=datetime.timezone.utc,
            ),
        )
        self.assertEqual(daily_end, self.now.astimezone(datetime.timezone.utc))
        self.assertEqual(
            weekly_start,
            datetime.datetime(
                2026,
                11,
                22,
                16,
                0,
                tzinfo=datetime.timezone.utc,
            ),
        )
        self.assertEqual(
            monthly_start,
            datetime.datetime(
                2026,
                10,
                31,
                16,
                0,
                tzinfo=datetime.timezone.utc,
            ),
        )
        self.assertEqual(
            yearly_start,
            datetime.datetime(
                2025,
                12,
                31,
                16,
                0,
                tzinfo=datetime.timezone.utc,
            ),
        )
        self.assertIsNone(all_time_start)

    def test_range_caption_reflects_calendar_window_through_today(self):
        self.assertEqual(
            dashboard._portal_engagement_range_caption("Weekly", self.now),
            "Showing: Nov 23 – Nov 28, 2026 (Mon–Sat, through now)",
        )
        self.assertEqual(
            dashboard._portal_engagement_range_caption("All Time", self.now),
            "Showing: All time",
        )

    def test_event_counts_are_filtered_by_choice_and_timeframe(self):
        events = [
            ("need_help", self.now - datetime.timedelta(hours=1)),
            ("need_help", self.now - datetime.timedelta(days=8)),
            ("no_help", self.now - datetime.timedelta(days=2)),
            ("no_help", self.now + datetime.timedelta(hours=1)),
        ]
        client = _Client(events)

        counts = dashboard._fetch_portal_engagement_event_counts(
            client,
            "Weekly",
            self.now,
        )

        self.assertEqual(counts, {"no_help_submitted": 1})
        self.assertEqual(client.tables, ["portal_engagement_events"])

    def test_help_request_count_uses_created_at_in_manila_time(self):
        rows = [
            {"created_at": "2026-11-27T16:00:00+00:00"},
            {"created_at": "2026-11-28T02:30:00+00:00"},
            {"created_at": "2026-11-27T23:59:59+08:00"},
            {"created_at": "2026-11-23T00:00:00+08:00"},
            {"created_at": "2026-11-22T23:59:59+08:00"},
            {"created_at": "2026-11-01T00:00:00+08:00"},
            {"created_at": "2026-10-31T23:59:59+08:00"},
            {"created_at": "2026-01-01T00:00:00+08:00"},
            {"created_at": "2025-12-31T23:59:59+08:00"},
            {"created_at": "2026-11-28T11:31:00+08:00"},
        ]
        expected_counts = {
            "Daily": 2,
            "Weekly": 4,
            "Monthly": 6,
            "Yearly": 8,
        }

        for timeframe, expected in expected_counts.items():
            with self.subTest(timeframe=timeframe):
                client = _HelpRequestClient(rows)
                count = dashboard._fetch_patient_help_request_count(
                    client,
                    timeframe,
                    self.now,
                )
                self.assertEqual(count, expected)
                self.assertEqual(client.tables, ["patient_help_requests"])
                filtered_rows = (
                    dashboard._filter_patient_help_requests_by_created_at(
                        rows,
                        timeframe,
                        self.now,
                    )
                )
                schedule_summary = (
                    dashboard._summarize_patient_help_request_schedules(
                        filtered_rows
                    )
                )
                self.assertEqual(len(filtered_rows), expected)
                self.assertEqual(
                    sum(count for _, count in schedule_summary["peak_slots"]),
                    count,
                )

    def test_schedule_analytics_use_help_request_created_at_rows_only(self):
        help_request_rows = [
            {
                "created_at": "2026-11-27T16:00:00Z",
                "updated_at": "2026-11-20T00:00:00Z",
                "approval_status": "Declined",
                "requested_date": "2026-11-30",
                "requested_time_slot": "08:00:00",
            },
            {
                "created_at": "2026-11-28T02:30:00Z",
                "updated_at": None,
                "approval_status": "Pending",
                "requested_date": "2026-12-01",
                "requested_time_slot": None,
            },
            {
                "created_at": "2026-11-27T15:59:59Z",
                "updated_at": "2026-11-28T03:00:00Z",
                "approval_status": "Pending",
                "requested_date": "2026-12-02",
                "requested_time_slot": "09:00:00",
            },
        ]
        appointment_rows = [
            {
                "created_at": "2026-11-28T02:30:00Z",
                "updated_at": None,
                "approval_status": "Scheduled",
                "requested_date": "2026-12-03",
                "requested_time_slot": "10:00:00",
            }
        ]

        analytics = dashboard._summarize_portal_request_analytics(
            help_request_rows,
            appointment_rows,
            "Daily",
            self.now,
        )

        self.assertEqual(
            sum(count for _, count in analytics["peak_slots"]),
            2,
        )
        self.assertEqual(
            analytics["peak_slots"],
            [("8:00 AM", 1), ("Unspecified", 1)],
        )
        self.assertEqual(analytics["most_requested_day"], ("Monday", 1))
        self.assertEqual(analytics["requested_date_count"], 2)

    def test_daily_request_filter_uses_latest_activity_in_manila_time(self):
        rows = [
            {
                "id": "updated-old-request",
                "created_at": "2026-11-01T00:00:00Z",
                "updated_at": "2026-11-27T16:00:00Z",
            },
            {
                "id": "activity-before-today",
                "created_at": "2026-11-27T15:59:59Z",
                "updated_at": None,
            },
            {
                "id": "updated-today",
                "created_at": "2026-11-01T00:00:00Z",
                "updated_at": "2026-11-28T03:29:00Z",
            },
            {
                "id": "created-today-updated-yesterday",
                "created_at": "2026-11-28T03:29:00Z",
                "updated_at": "2026-11-27T15:59:59Z",
            },
            {
                "id": "future-in-manila",
                "created_at": "2026-11-01T00:00:00Z",
                "updated_at": "2026-11-28T03:31:00Z",
            },
        ]

        filtered_rows = dashboard._filter_portal_request_rows_by_activity_at(
            rows,
            "Daily",
            self.now,
        )

        self.assertEqual(
            [row["id"] for row in filtered_rows],
            ["updated-old-request", "updated-today"],
        )

    def test_latest_activity_is_used_for_each_request_timeframe(self):
        rows = [
            {
                "id": "updated-old-request",
                "created_at": "2026-01-01T00:00:00Z",
                "updated_at": "2026-11-28T00:01:00+08:00",
            }
        ]

        for timeframe in ("Daily", "Weekly", "Monthly", "Yearly"):
            with self.subTest(timeframe=timeframe):
                filtered_rows = (
                    dashboard._filter_portal_request_rows_by_activity_at(
                        rows,
                        timeframe,
                        self.now,
                    )
                )
                self.assertEqual(
                    [row["id"] for row in filtered_rows],
                    ["updated-old-request"],
                )

    def test_request_outcome_status_aliases_are_case_insensitive(self):
        statuses = (
            "CONFIRMED",
            "scheduled",
            "Appointed",
            "RESCHEDULED",
            "Resched",
            "DONE",
            "completed",
            "CANCELLED",
            "declined",
            "No-show",
            "NO_SHOW",
        )
        summary = dashboard._summarize_portal_request_rows(
            [
                {"approval_status": status, "created_at": "2026-11-28T00:00:00Z"}
                for status in statuses
            ]
        )

        self.assertEqual(
            summary["outcomes"],
            {
                "Pending / Awaiting": 0,
                "Confirmed / Scheduled": 3,
                "Rescheduled": 2,
                "Done": 2,
                "Cancelled": 2,
                "No-show": 2,
            },
        )

    def test_request_analytics_normalize_status_and_schedule_values(self):
        summary = dashboard._summarize_portal_request_rows(
            [
                {
                    "approval_status": "Pending",
                    "created_at": "2026-11-28T00:10:00+08:00",
                    "requested_date": "2026-11-30",
                    "requested_time_slot": "08:00:00",
                },
                {
                    "approval_status": "Scheduled",
                    "created_at": "2026-11-28T01:10:00+08:00",
                    "requested_date": "2026-11-30",
                    "requested_time_slot": "8:00 AM",
                },
                {
                    "approval_status": "Completed",
                    "created_at": "2026-11-29T01:10:00+08:00",
                    "requested_date": "2026-12-01",
                    "requested_time_slot": "13:00:00",
                },
                {
                    "approval_status": "Declined",
                    "created_at": "2026-11-28T02:10:00+08:00",
                    "requested_date": "2026-12-02",
                    "requested_time_slot": "08:00",
                },
                {
                    "approval_status": "No-show",
                    "created_at": "2026-11-27T02:10:00+08:00",
                    "requested_date": "2026-12-04",
                    "requested_time_slot": None,
                },
            ]
        )

        self.assertEqual(
            summary["outcomes"],
            {
                "Pending / Awaiting": 1,
                "Confirmed / Scheduled": 1,
                "Rescheduled": 0,
                "Done": 1,
                "Cancelled": 1,
                "No-show": 1,
            },
        )
        self.assertEqual(summary["peak_slots"], [("8:00 AM", 3), ("1:00 PM", 1)])
        self.assertEqual(summary["most_requested_day"], ("Monday", 2))
        self.assertEqual(summary["requested_date_count"], 4)

    def test_daily_requested_day_caption_avoids_single_date_comparison(self):
        self.assertEqual(
            dashboard._format_most_requested_day(
                {
                    "most_requested_day": ("Monday", 3),
                    "requested_date_count": 1,
                },
                "Daily",
            ),
            "Scheduled weekday: Monday · 3 requests",
        )
        self.assertEqual(
            dashboard._format_most_requested_day(
                {
                    "most_requested_day": None,
                    "requested_date_count": 0,
                },
                "Daily",
            ),
            "Scheduled weekday: No scheduled dates · 0 requests",
        )
        self.assertEqual(
            dashboard._format_most_requested_day(
                {
                    "most_requested_day": ("Thursday", 4),
                    "requested_date_count": 2,
                },
                "Daily",
            ),
            "Most requested day: Thursday · 4 requests",
        )

    def test_engagement_panel_switches_from_singleton_to_period_counts(self):
        source = "\n".join(
            [
                "import sys",
                (
                    "sys.path.insert(0, "
                    f"{str(Path(__file__).resolve().parents[1])!r})"
                ),
                "from views import dashboard",
                "dashboard._load_portal_engagement_event_counts = "
                "lambda _timeframe: ({'no_help_submitted': 2}, None)",
                "dashboard._load_patient_help_request_count = "
                "lambda _timeframe: (3, None)",
                "dashboard._load_portal_request_analytics = "
                "lambda _timeframe: ({'outcomes': {"
                "'Pending / Awaiting': 0, 'Confirmed / Scheduled': 0, "
                "'Rescheduled': 0, 'Done': 0, 'Cancelled': 0, 'No-show': 0"
                "}, 'peak_slots': [], 'most_requested_day': None, "
                "'requested_date_count': 0}, None)",
                "dashboard._load_portal_request_analytics.clear = "
                "lambda: None",
                "dashboard._render_portal_engagement({",
                "    'counts': {'need_help_submitted': 10, "
                "'no_help_submitted': 9},",
                "    'journal_accounts': [],",
                "})",
            ]
        )
        app = AppTest.from_string(source).run()
        self.assertFalse(app.exception)
        markdown_values = [element.value for element in app.markdown]
        self.assertFalse(
            any("Portal Engagement" in value for value in markdown_values)
        )
        self.assertFalse(
            any("Last refreshed" in value for value in markdown_values)
        )
        self.assertEqual(
            app.get_by_key("portal_engagement_timeframe").value,
            "All Time",
        )
        self.assertEqual([metric.value for metric in app.metric], ["10", "9", "0"])

        app.get_by_key("portal_engagement_timeframe").set_value("Daily").run()
        self.assertFalse(app.exception)
        self.assertEqual([metric.value for metric in app.metric], ["3", "2", "0"])


if __name__ == "__main__":
    unittest.main()
