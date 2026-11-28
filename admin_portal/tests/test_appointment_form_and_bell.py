import importlib
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
appointments = importlib.import_module("views.appointments")
home_dashboard = importlib.import_module("views.home_dashboard")


class AppointmentFormAndBellTests(unittest.TestCase):
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
