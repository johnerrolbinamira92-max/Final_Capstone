import importlib
import sys
import unittest
from pathlib import Path

import pandas as pd
from streamlit.testing.v1 import AppTest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
encode = importlib.import_module("views.encode")
manage = importlib.import_module("views.manage")
record_tables = importlib.import_module("views.record_tables")


class PatientInputValidationTests(unittest.TestCase):
    def test_mobile_number_requires_eleven_digits_starting_with_09(self):
        self.assertTrue(encode._is_valid_contact_number(""))
        self.assertTrue(encode._is_valid_contact_number("09123456789"))
        for value in ("0912345678", "091234567890", "09123A56789", "+639123456789"):
            with self.subTest(value=value):
                self.assertFalse(encode._is_valid_contact_number(value))

    def test_nonnegative_numeric_validation_rejects_invalid_values(self):
        self.assertTrue(encode._is_valid_nonnegative_number(None))
        self.assertTrue(encode._is_valid_nonnegative_number(25.5))
        self.assertFalse(encode._is_valid_nonnegative_number(-1))
        self.assertFalse(
            encode._is_valid_nonnegative_number(2.5, integer=True)
        )
        self.assertFalse(
            encode._is_valid_nonnegative_number(121, integer=True, max_value=120)
        )
        self.assertFalse(encode._is_valid_nonnegative_number(float("inf")))

    def test_encode_submission_collects_contact_and_numeric_errors(self):
        errors = encode._encode_validation_errors(
            contact_number="09123A56789",
            calculated_age=121,
            household_member_count=2.5,
            annual_income=-1,
            poverty_threshold=float("inf"),
            family_composition=pd.DataFrame(columns=record_tables.FAMILY_COLUMNS),
        )

        self.assertEqual(len(errors), 5)
        self.assertTrue(any("Contact Number" in error for error in errors))
        self.assertTrue(any("Age" in error for error in errors))
        self.assertTrue(
            any("Household Members" in error for error in errors)
        )
        self.assertTrue(any("annual income" in error for error in errors))
        self.assertTrue(any("Poverty threshold" in error for error in errors))

    def test_family_age_and_monthly_income_are_validated_by_row(self):
        family = pd.DataFrame(
            [
                {"Age": 18, "Monthly Income": 1250.50},
                {"Age": 18.5, "Monthly Income": -1},
                {"Age": 121, "Monthly Income": "not a number"},
            ]
        )

        errors = record_tables.validate_family_composition(family)

        self.assertEqual(len(errors), 4)
        self.assertTrue(all("row 2" in errors[index].lower() for index in (0, 1)))
        self.assertTrue(all("row 3" in error.lower() for error in errors[2:]))

    def test_person_name_validation_accepts_names_and_rejects_digits_symbols(self):
        for value in ("José Ñuñez", "Anne-Marie O'Neil", "Dela Cruz Jr."):
            with self.subTest(value=value):
                self.assertTrue(record_tables.is_valid_person_name(value))
        for value in ("Mary2", "Jane_Doe", "John×Doe", "Ana/Lee", "---"):
            with self.subTest(value=value):
                self.assertFalse(record_tables.is_valid_person_name(value))

    def test_family_and_patient_name_errors_are_reported_on_save(self):
        family = pd.DataFrame(
            [{"Name": "Kid 2", "Age": 8, "Monthly Income": 0}]
        )
        family_errors = record_tables.validate_family_composition(family)
        self.assertEqual(len(family_errors), 1)
        self.assertIn("row 1", family_errors[0].lower())

        errors = encode._encode_validation_errors(
            contact_number="09123456789",
            calculated_age=25,
            household_member_count=3,
            annual_income=1000,
            poverty_threshold=500,
            family_composition=pd.DataFrame(
                columns=record_tables.FAMILY_COLUMNS
            ),
            name_fields={"First Name": "Ana2"},
        )
        self.assertEqual(len(errors), 1)
        self.assertIn("First Name", errors[0])

    def test_search_edit_sections_validate_person_and_worker_names(self):
        identifying_errors = manage._view_section_validation_errors(
            "identifying",
            {
                "first_name": "Juan3",
                "middle_name": "",
                "last_name": "Dela Cruz",
                "extension_name": "",
                "calculated_age": 25,
            },
        )
        worker_errors = manage._view_section_validation_errors(
            "referral",
            {"referral_noted_by": "Admin 2"},
        )

        self.assertEqual(len(identifying_errors), 1)
        self.assertEqual(len(worker_errors), 1)

    def test_dismissing_log_session_resets_substate_but_keeps_patient_open(self):
        state = {
            "manage_selected_patient_id": 42,
            "manage_return_session_patient_id": 42,
            "return-session-date-42": "2026-11-28",
            "return-session-complaint-patient-42": "Example",
        }

        self.assertTrue(manage._reset_return_session_substate(state, 42))
        self.assertEqual(state["manage_selected_patient_id"], 42)
        self.assertNotIn("manage_return_session_patient_id", state)
        self.assertNotIn("return-session-date-42", state)
        self.assertNotIn("return-session-complaint-patient-42", state)
        self.assertFalse(manage._reset_return_session_substate(state, 42))

    def test_clearing_restricted_name_lookup_resets_search(self):
        app = AppTest.from_string(
            "\n".join(
                [
                    "import streamlit as st",
                    "from views.manage import _clear_patient_name_lookup",
                    "st.text_input('Restricted Name Lookup', type='password', key='patient_name_lookup_query')",
                    "st.button('✕', key='clear-name', on_click=_clear_patient_name_lookup, disabled=not st.session_state.get('patient_name_lookup_query'))",
                ]
            )
        )
        app.session_state["patient_name_lookup_query"] = "Example Patient"
        app.run()

        app.button(key="clear-name").click().run()

        self.assertEqual(app.session_state["patient_name_lookup_query"], "")


if __name__ == "__main__":
    unittest.main()
