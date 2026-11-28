import datetime
import importlib
import sys
import unittest
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
dashboard = importlib.import_module("views.dashboard")


class PatientStatisticsTests(unittest.TestCase):
    def setUp(self):
        self.now = datetime.datetime(
            2026,
            11,
            28,
            11,
            30,
            tzinfo=dashboard.PORTAL_ENGAGEMENT_TIMEZONE,
        )

    def test_top_age_group_share_uses_all_filtered_records(self):
        data = pd.DataFrame({"calculated_age": [18, 19, 24, 55, None]})

        summary, known_age_total = dashboard._top_age_group_summary(data)

        self.assertEqual(summary, "18–24 yrs · 60%")
        self.assertEqual(known_age_total, 4)

    def test_top_age_group_handles_empty_and_unknown_age_records(self):
        empty_data = pd.DataFrame({"calculated_age": pd.Series(dtype="float64")})
        unknown_age_data = pd.DataFrame({"calculated_age": [None, -1]})

        self.assertEqual(
            dashboard._top_age_group_summary(empty_data),
            ("No records yet", 0),
        )
        self.assertEqual(
            dashboard._top_age_group_summary(unknown_age_data),
            ("No age data", 0),
        )

    def test_minor_summary_counts_under_eighteen_and_uses_filtered_total(self):
        data = pd.DataFrame({"calculated_age": [12, 17, 18, None, -1, 42, 63]})
        empty_data = pd.DataFrame(
            {"calculated_age": pd.Series(dtype="float64")}
        )

        self.assertEqual(
            dashboard._minor_age_summary(
                dashboard._age_group_counts(data),
                len(data),
            ),
            "2 · 29%",
        )
        self.assertEqual(
            dashboard._minor_age_summary(
                dashboard._age_group_counts(empty_data),
                len(empty_data),
            ),
            "0 · 0%",
        )
        self.assertEqual(
            dashboard._minor_age_summary(
                dashboard._age_group_counts(
                    pd.DataFrame({"calculated_age": [None, -1]})
                ),
                2,
            ),
            "0 · 0%",
        )

    def test_registration_trends_use_manila_dates_and_monday_weeks(self):
        data = pd.DataFrame(
            {
                "date_registered": [
                    "2026-11-27T16:30:00Z",
                    "2026-11-27",
                    "2026-11-16",
                    "2026-11-23",
                ]
            }
        )

        daily = dashboard._registration_trend_data(data, "Daily", self.now)
        weekly = dashboard._registration_trend_data(data, "Weekly", self.now)

        daily_counts = dict(zip(daily["Label"], daily["Registrations"]))
        weekly_counts = dict(zip(weekly["Label"], weekly["Registrations"]))
        self.assertEqual(daily_counts["Nov 28"], 1)
        self.assertEqual(daily_counts["Nov 27"], 1)
        self.assertEqual(weekly_counts["Nov 16"], 1)
        self.assertEqual(weekly_counts["Nov 23"], 3)

    def test_monthly_registration_labels_are_unique_calendar_months(self):
        data = pd.DataFrame(
            {
                "date_registered": [
                    "2026-06-05",
                    "2026-07-05",
                    "2026-08-05",
                    "2026-09-05",
                    "2026-10-05",
                    "2026-11-05",
                ]
            }
        )

        trend = dashboard._registration_trend_data(
            data,
            "Monthly",
            self.now,
        )

        self.assertEqual(
            trend["Label"].tolist(),
            ["Jun", "Jul", "Aug", "Sep", "Oct", "Nov"],
        )
        self.assertEqual(trend["Registrations"].tolist(), [1, 1, 1, 1, 1, 1])


if __name__ == "__main__":
    unittest.main()
