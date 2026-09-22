import json
import os
import tempfile
import unittest

from state_store import StateStore


class StateStoreTests(unittest.TestCase):
    def test_state_survives_reload(self):
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, "state.json")
            store = StateStore(path)
            store.record_run_started()
            store.record_host(
                "example.ddns.net",
                "old",
                "new",
                {
                    "expires_in_days": None,
                    "estimated_days_until_expiry": 30,
                    "estimated_expiration": "2026-10-21T00:00:00+00:00",
                },
            )
            store.record_success(
                "2026-10-20T00:00:00+00:00",
                {"example.ddns.net": 30},
                30,
            )

            reloaded = StateStore(path).state
            self.assertEqual(
                reloaded["hosts"]["example.ddns.net"]["data_update"], "new"
            )
            self.assertEqual(reloaded["next_renewal_days"], 30)
            self.assertIsNotNone(reloaded["last_success"])
            self.assertIsNone(reloaded["last_error"])

    def test_failure_is_persisted_as_structured_data(self):
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, "state.json")
            store = StateStore(path)
            store.record_failure(RuntimeError("navigation failed"))

            with open(path, encoding="utf-8") as state_file:
                persisted = json.load(state_file)
            self.assertEqual(persisted["last_error"]["type"], "RuntimeError")
            self.assertEqual(persisted["last_error"]["message"], "navigation failed")

    def test_scheduled_check_survives_reload(self):
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, "state.json")
            store = StateStore(path)
            scheduled = "2026-09-26T11:43:00-06:00"
            store.record_next_check(scheduled)

            self.assertEqual(StateStore(path).state["next_check"], scheduled)

    def test_inventory_tracks_current_and_removed_hosts(self):
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, "state.json")
            store = StateStore(path)
            store.record_inventory({
                "first.ddns.net": {
                    "host_id": "1",
                    "data_update": "old",
                    "expires_in_days": None,
                    "renewal_available": False,
                }
            })
            store.record_inventory({
                "second.ddns.net": {
                    "host_id": "2",
                    "data_update": "new",
                    "expires_in_days": 5,
                    "renewal_available": True,
                }
            })
            reloaded = StateStore(path).state["hosts"]
            self.assertFalse(reloaded["first.ddns.net"]["active"])
            self.assertTrue(reloaded["second.ddns.net"]["active"])


if __name__ == "__main__":
    unittest.main()
