import unittest
from datetime import datetime
from zoneinfo import ZoneInfo

from host_timing import derive_cycle_timing, parse_data_update


class HostTimingTests(unittest.TestCase):
    def test_parses_noip_display_timestamp(self):
        parsed = parse_data_update(
            "Sep 17, 2026 13:38:34", timezone_name="America/Costa_Rica"
        )
        self.assertEqual(parsed.year, 2026)
        self.assertEqual(parsed.utcoffset().total_seconds(), -21600)

    def test_derives_separately_labeled_cycle_estimate(self):
        now = datetime(2026, 9, 22, 12, tzinfo=ZoneInfo("America/Costa_Rica"))
        timing = derive_cycle_timing(
            "Sep 17, 2026 13:38:34",
            now=now,
            timezone_name="America/Costa_Rica",
        )
        self.assertEqual(timing["estimated_days_until_expiry"], 26)
        self.assertTrue(timing["estimated_expiration"].startswith("2026-10-17"))

    def test_unparseable_timestamp_produces_no_estimate(self):
        timing = derive_cycle_timing("not a date", timezone_name="UTC")
        self.assertIsNone(timing["estimated_expiration"])
        self.assertIsNone(timing["estimated_days_until_expiry"])

    def test_iso_timestamp_preserves_explicit_offset(self):
        parsed = parse_data_update("2026-09-17T13:38:34+02:00")
        self.assertEqual(parsed.utcoffset().total_seconds(), 7200)

    def test_expired_cycle_is_clamped_to_zero_days(self):
        now = datetime(2026, 11, 1, tzinfo=ZoneInfo("UTC"))
        timing = derive_cycle_timing(
            "Sep 17, 2026 13:38:34",
            now=now,
            timezone_name="UTC",
        )
        self.assertEqual(timing["estimated_days_until_expiry"], 0)

    def test_alternate_comma_format_is_accepted(self):
        parsed = parse_data_update("Sep 17, 2026, 13:38:34", timezone_name="UTC")
        self.assertEqual(parsed.day, 17)


if __name__ == "__main__":
    unittest.main()
