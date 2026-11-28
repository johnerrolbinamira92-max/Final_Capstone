import importlib
import sqlite3
import sys
import unittest
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
patient_care_status = importlib.import_module("views.patient_care_status")


class PatientCareStatusTests(unittest.TestCase):
    def test_deceased_priority_and_latest_care_date_classification(self):
        today = date(2026, 3, 2)
        connection = sqlite3.connect(":memory:")
        connection.row_factory = sqlite3.Row
        connection.executescript(
            """
            CREATE TABLE patients (
                patient_id INTEGER PRIMARY KEY,
                status TEXT,
                date_encoded TEXT,
                date_registered TEXT,
                created_at TEXT
            );
            CREATE TABLE patient_return_sessions (
                patient_id INTEGER,
                session_date TEXT
            );
            INSERT INTO patients VALUES
                (1, 'Deceased', '2026-03-02', '2020-01-01', NULL),
                (2, 'Alive', NULL, '2020-01-01', NULL),
                (3, 'Alive', NULL, '2025-03-02', NULL),
                (4, 'Alive', NULL, '2025-03-01', NULL),
                (5, 'Alive', NULL, NULL, '2026-03-01T18:00:00Z'),
                (6, 'Alive', NULL, NULL, NULL),
                (7, 'Alive', '2026-03-01', '2020-01-01', NULL);
            INSERT INTO patient_return_sessions VALUES
                (1, '2026-03-02'),
                (2, '2025-03-02');
            """
        )

        statuses = patient_care_status.load_patient_care_statuses(
            connection, today=today
        )

        self.assertEqual(statuses[1], patient_care_status.CARE_STATUS_DECEASED)
        self.assertEqual(statuses[2], patient_care_status.CARE_STATUS_ACTIVE)
        self.assertEqual(statuses[3], patient_care_status.CARE_STATUS_ACTIVE)
        self.assertEqual(
            statuses[4],
            patient_care_status.CARE_STATUS_LOST_TO_FOLLOW_UP,
        )
        self.assertEqual(statuses[5], patient_care_status.CARE_STATUS_ACTIVE)
        self.assertEqual(
            statuses[6],
            patient_care_status.CARE_STATUS_LOST_TO_FOLLOW_UP,
        )
        self.assertEqual(statuses[7], patient_care_status.CARE_STATUS_ACTIVE)
        connection.close()

    def test_new_records_use_the_registration_date_default(self):
        connection = sqlite3.connect(":memory:")
        connection.row_factory = sqlite3.Row
        connection.executescript(
            """
            CREATE TABLE patients (
                patient_id INTEGER PRIMARY KEY,
                status TEXT,
                date_registered TEXT DEFAULT CURRENT_DATE
            );
            INSERT INTO patients (status) VALUES ('Alive');
            """
        )

        statuses = patient_care_status.load_patient_care_statuses(
            connection, today=date.today()
        )

        self.assertEqual(statuses[1], patient_care_status.CARE_STATUS_ACTIVE)
        connection.close()


if __name__ == "__main__":
    unittest.main()
