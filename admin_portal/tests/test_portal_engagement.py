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

    def table(self, _table_name):
        return _Query(self.events)


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

        counts = dashboard._fetch_portal_engagement_event_counts(
            _Client(events),
            "Weekly",
            self.now,
        )

        self.assertEqual(
            counts,
            {
                "need_help_submitted": 1,
                "no_help_submitted": 1,
            },
        )

    def test_daily_request_filter_uses_created_at_in_manila_time(self):
        rows = [
            {
                "id": "local-midnight",
                "created_at": "2026-11-27T16:00:00Z",
            },
            {
                "id": "earlier-in-manila",
                "created_at": "2026-11-27T15:59:59Z",
            },
            {
                "id": "later-today",
                "created_at": "2026-11-28T03:29:00Z",
            },
            {
                "id": "future-in-manila",
                "created_at": "2026-11-28T03:31:00Z",
            },
        ]

        filtered_rows = dashboard._filter_portal_request_rows_by_created_at(
            rows,
            "Daily",
            self.now,
        )

        self.assertEqual(
            [row["id"] for row in filtered_rows],
            ["local-midnight", "later-today"],
        )

    def test_request_analytics_normalize_status_and_schedule_values(self):
        summary = dashboard._summarize_portal_request_rows(
            [
                {
                    "approval_status": "Pending",
                    "created_at": "2026-11-28T00:10:00+08:00",
                    "requested_time_slot": "08:00:00",
                },
                {
                    "approval_status": "Scheduled",
                    "created_at": "2026-11-28T01:10:00+08:00",
                    "requested_time_slot": "8:00 AM",
                },
                {
                    "approval_status": "Completed",
                    "created_at": "2026-11-29T01:10:00+08:00",
                    "requested_time_slot": "13:00:00",
                },
                {
                    "approval_status": "Declined",
                    "created_at": "2026-11-28T02:10:00+08:00",
                    "requested_time_slot": "08:00",
                },
                {
                    "approval_status": "No-show",
                    "created_at": "2026-11-27T02:10:00+08:00",
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
        self.assertEqual(summary["busiest_day"], ("Saturday", 3))

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
                "lambda _timeframe: ({'need_help_submitted': 3, "
                "'no_help_submitted': 2}, None)",
                "dashboard._load_portal_request_analytics = "
                "lambda _timeframe: ({'outcomes': {"
                "'Pending / Awaiting': 0, 'Confirmed / Scheduled': 0, "
                "'Rescheduled': 0, 'Done': 0, 'Cancelled': 0, 'No-show': 0"
                "}, 'peak_slots': [], 'busiest_day': None}, None)",
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
