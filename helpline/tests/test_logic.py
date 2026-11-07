from datetime import datetime, time
import unittest

from logic import MANILA, combine_schedule, normalize_phone, valid_phone, valid_schedule


class LogicTests(unittest.TestCase):
    def test_normalize_and_validate_philippine_mobile_number(self) -> None:
        self.assertEqual(normalize_phone("0917 123-4567"), "09171234567")
        self.assertTrue(valid_phone("0917 123-4567"))
        self.assertTrue(valid_phone("+639171234567"))
        self.assertFalse(valid_phone("12345"))

    def test_weekday_slot_is_valid(self) -> None:
        now = datetime(2026, 1, 5, 8, 0, tzinfo=MANILA)
        schedule = combine_schedule(now.date(), time(9, 0))
        self.assertTrue(valid_schedule(schedule, now))

    def test_weekend_and_non_half_hour_slots_are_invalid(self) -> None:
        now = datetime(2026, 1, 5, 8, 0, tzinfo=MANILA)
        saturday = datetime(2026, 1, 10, 9, 0, tzinfo=MANILA)
        odd_minute = datetime(2026, 1, 6, 9, 15, tzinfo=MANILA)
        self.assertFalse(valid_schedule(saturday, now))
        self.assertFalse(valid_schedule(odd_minute, now))


if __name__ == "__main__":
    unittest.main()
