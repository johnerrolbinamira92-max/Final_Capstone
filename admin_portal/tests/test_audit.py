import importlib
import sys
import unittest
from datetime import date
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
audit = importlib.import_module("views.audit")


class AuditTrailTests(unittest.TestCase):
    def test_action_categories_cover_record_session_and_admin_actions(self):
        self.assertEqual(
            audit._available_action_categories(
                [
                    "APPOINTMENT SCHEDULED",
                    "PATIENT RETURN SESSION LOGGED",
                    "PATIENT RECORD EDITED",
                    "PATIENT RECORD ADDED",
                    "ADMIN LOGIN",
                    "EXPORT BACKUP",
                ]
            ),
            [
                "Login / Logout",
                "Record Created",
                "Record Updated",
                "Session Logged",
                "Appointment / Callback Action",
                "Export / Backup",
            ],
        )

    def test_filters_use_manila_date_search_details_and_newest_first(self):
        logs = pd.DataFrame(
            [
                {
                    "log_id": 10,
                    "timestamp": "2026-03-01T15:59:00Z",
                    "action_type": "PATIENT RECORD ADDED",
                    "details": "Added patient record for Maya (record 10).",
                },
                {
                    "log_id": 3,
                    "timestamp": "2026-03-01T17:00:00Z",
                    "action_type": "APPOINTMENT SCHEDULED",
                    "details": "Scheduled an appointment for Maya.",
                },
                {
                    "log_id": 2,
                    "timestamp": "2026-03-01T16:30:00Z",
                    "action_type": "PATIENT RECORD EDITED",
                    "details": "Edited patient record for Kai (record 2).",
                },
            ]
        )

        all_entries = audit._filter_audit_entries(logs)
        self.assertEqual(
            all_entries["Action"].tolist(),
            ["Appointment scheduled", "Patient record edited", "Patient record added"],
        )

        filtered = audit._filter_audit_entries(
            logs,
            action_filter="Appointment / Callback Action",
            selected_date=date(2026, 3, 2),
            search_text="Maya",
        )
        self.assertEqual(len(filtered), 1)
        self.assertEqual(filtered.iloc[0]["Category"], "Appointment / Callback Action")
        self.assertIn("Mar 2, 2026", filtered.iloc[0]["Date and time (Philippine Time)"])


if __name__ == "__main__":
    unittest.main()
