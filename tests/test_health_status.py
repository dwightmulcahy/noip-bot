import unittest
from datetime import datetime, timedelta, timezone

from health_status import evaluate_health


class HealthStatusTests(unittest.TestCase):
    def setUp(self):
        self.now = datetime(2026, 9, 22, 12, tzinfo=timezone.utc)

    def healthy_state(self):
        return {
            "last_run": (self.now - timedelta(minutes=1)).isoformat(),
            "last_success": (self.now - timedelta(seconds=30)).isoformat(),
            "last_error": None,
            "next_check": (self.now + timedelta(days=1)).isoformat(),
            "next_renewal_days": 0,
            "hosts": {"example.ddns.net": {}},
        }

    def test_current_success_and_future_schedule_are_healthy(self):
        result = evaluate_health(self.healthy_state(), self.now)
        self.assertTrue(result["healthy"])
        self.assertEqual(result["host_count"], 1)

    def test_newer_failure_is_unhealthy(self):
        state = self.healthy_state()
        state["last_error"] = {
            "timestamp": self.now.isoformat(),
            "message": "login failed",
        }
        result = evaluate_health(state, self.now)
        self.assertFalse(result["healthy"])
        self.assertIn("login failed", result["reasons"])

    def test_overdue_or_missing_schedule_is_unhealthy(self):
        state = self.healthy_state()
        state["next_check"] = (self.now - timedelta(hours=2)).isoformat()
        self.assertFalse(evaluate_health(state, self.now)["healthy"])
        state["next_check"] = None
        self.assertFalse(evaluate_health(state, self.now)["healthy"])

    def test_old_failure_before_success_does_not_poison_health(self):
        state = self.healthy_state()
        state["last_error"] = {
            "timestamp": (self.now - timedelta(minutes=2)).isoformat(),
            "message": "old failure",
        }
        result = evaluate_health(state, self.now)
        self.assertTrue(result["healthy"])

    def test_overdue_grace_boundary_is_honored(self):
        state = self.healthy_state()
        state["next_check"] = (self.now - timedelta(seconds=3599)).isoformat()
        self.assertTrue(evaluate_health(state, self.now, 3600)["healthy"])
        state["next_check"] = (self.now - timedelta(seconds=3601)).isoformat()
        self.assertFalse(evaluate_health(state, self.now, 3600)["healthy"])

    def test_host_count_excludes_inactive_history(self):
        state = self.healthy_state()
        state["hosts"] = {
            "active.ddns.net": {"active": True},
            "removed.ddns.net": {"active": False},
        }
        result = evaluate_health(state, self.now)
        self.assertEqual(result["host_count"], 1)
        self.assertEqual(result["total_host_count"], 2)

    def test_malformed_success_timestamp_is_unhealthy(self):
        state = self.healthy_state()
        state["last_success"] = "not-a-time"
        result = evaluate_health(state, self.now)
        self.assertFalse(result["healthy"])


if __name__ == "__main__":
    unittest.main()
