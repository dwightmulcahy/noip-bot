import unittest
from datetime import datetime, timedelta, timezone

from scheduling import days_until_check, future_check


class SchedulingTests(unittest.TestCase):
    def test_check_delay_never_becomes_zero_or_negative(self):
        self.assertEqual(days_until_check(2, 4), 1)
        self.assertEqual(days_until_check(6, 4), 1)
        self.assertEqual(days_until_check(10, 4), 4)

    def test_fallback_is_used_without_expiration(self):
        self.assertEqual(days_until_check(0, 3), 3)

    def test_future_schedule_is_restored(self):
        now = datetime(2026, 9, 22, tzinfo=timezone.utc)
        expected = now + timedelta(days=1)
        self.assertEqual(future_check(expected.isoformat(), now), expected)

    def test_overdue_or_invalid_schedule_is_not_restored(self):
        now = datetime(2026, 9, 22, tzinfo=timezone.utc)
        self.assertIsNone(future_check((now - timedelta(seconds=1)).isoformat(), now))
        self.assertIsNone(future_check("invalid", now))
        self.assertIsNone(future_check(None, now))


if __name__ == "__main__":
    unittest.main()
