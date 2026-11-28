import importlib
import sys
import unittest
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
dashboard = importlib.import_module("views.dashboard")


class PatientStatisticsTests(unittest.TestCase):
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


if __name__ == "__main__":
    unittest.main()
