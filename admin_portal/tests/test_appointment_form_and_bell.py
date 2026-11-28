import importlib
import sys
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from streamlit.testing.v1 import AppTest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
appointments = importlib.import_module("views.appointments")
home_dashboard = importlib.import_module("views.home_dashboard")


class AppointmentFormAndBellTests(unittest.TestCase):
    def test_home_search_runs_from_text_input_change(self):
        app = AppTest.from_string(
            "\n".join(
                [
                    "import streamlit as st",
                    "import views.home_dashboard as home",
                    "home._search_local_patients = lambda query: [{'query': query}]",
                    "st.text_input('Search', key='home_search_query', on_change=home._submit_home_quick_search)",
                ]
            )
        )
        app.run()

        app.text_input(key="home_search_query").set_value("Maria").run()

        self.assertEqual(app.session_state["home_quick_search_query"], "Maria")
        self.assertTrue(app.session_state["home_quick_search_open"])
        self.assertEqual(
            app.session_state["home_quick_search_results"],
            [{"query": "Maria"}],
        )

    def test_appointment_reads_are_cached_and_invalidated_after_writes(self):
        appointments._invalidate_schedule_data_caches()
        client = Mock()
        query = Mock()
        query.select.return_value = query
        query.order.return_value = query
        query.range.return_value = query
        query.execute.return_value = Mock(data=[])
        client.table.return_value = query

        try:
            appointments._load_appointments(client)
            appointments._load_appointments(client)
            self.assertEqual(client.table.call_count, 1)

            appointments._invalidate_schedule_data_caches()
            appointments._load_appointments(client)
            self.assertEqual(client.table.call_count, 2)
        finally:
            appointments._invalidate_schedule_data_caches()

    def test_schedule_cache_invalidation_clears_all_streamlit_data(self):
        with patch.object(appointments.st.cache_data, "clear") as clear_all:
            appointments._invalidate_schedule_data_caches()

        clear_all.assert_called_once_with()

    def test_contact_number_requires_exactly_eleven_ascii_digits(self):
        self.assertTrue(appointments._is_valid_contact_number("09123456789"))
        for contact_number in (
            "0912345678",
            "091234567890",
            "09123A56789",
            "０９１２３４５６７８９",
        ):
            with self.subTest(contact_number=contact_number):
                self.assertFalse(
                    appointments._is_valid_contact_number(contact_number)
                )

    def test_only_unresponded_patient_help_requests_are_bell_alerts(self):
        requests = [
            {"kind": "help_request", "status": "Pending"},
            {"kind": "help_request", "status": "Awaiting"},
            {"kind": "help_request", "status": "awaiting confirmation"},
            {"kind": "help_request", "status": "Confirmed"},
            {"kind": "appointment", "status": "Pending"},
            {"kind": "appointment", "status": "Scheduled"},
        ]

        self.assertEqual(
            [
                request["status"]
                for request in requests
                if home_dashboard._is_unresponded_patient_request(request)
            ],
            ["Pending", "Awaiting", "awaiting confirmation"],
        )


if __name__ == "__main__":
    unittest.main()
