import unittest
from datetime import datetime, timedelta, timezone

from scheduling import cap_future_check, days_until_check, future_check


class SchedulingTests(unittest.TestCase):
    def test_check_delay_never_becomes_zero_or_negative(self):
        self.assertEqual(days_until_check(2, 4), 1)
        self.assertEqual(days_until_check(6, 4), 1)
        self.assertEqual(days_until_check(10, 4), 4)
        self.assertEqual(days_until_check(30, 4), 5)

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

    def test_naive_future_timestamp_is_rejected(self):
        now = datetime(2026, 9, 22, tzinfo=timezone.utc)
        self.assertIsNone(future_check("2026-09-23T12:00:00", now))

    def test_invalid_fallback_is_clamped_to_one_day(self):
        self.assertEqual(days_until_check(0, 0), 1)
        self.assertEqual(days_until_check(None, -4), 1)

    def test_fallback_and_estimate_respect_custom_cap(self):
        self.assertEqual(days_until_check(30, 9, max_interval_days=3), 3)
        self.assertEqual(days_until_check(0, 9, max_interval_days=3), 3)

    def test_invalid_cap_is_clamped_to_one_day(self):
        self.assertEqual(days_until_check(30, 4, max_interval_days=0), 1)
        self.assertEqual(days_until_check(30, 4, max_interval_days=-5), 1)

    def test_restored_schedule_is_shortened_to_safety_cap(self):
        now = datetime(2026, 9, 22, tzinfo=timezone.utc)
        scheduled = now + timedelta(days=20)
        self.assertEqual(
            cap_future_check(scheduled, now, max_interval_days=5),
            now + timedelta(days=5),
        )

    def test_restored_schedule_inside_cap_is_unchanged(self):
        now = datetime(2026, 9, 22, tzinfo=timezone.utc)
        scheduled = now + timedelta(days=2)
        self.assertEqual(cap_future_check(scheduled, now, 5), scheduled)
        self.assertIsNone(cap_future_check(None, now, 5))


if __name__ == "__main__":
    unittest.main()
