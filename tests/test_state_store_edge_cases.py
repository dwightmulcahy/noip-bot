import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from state_store import StateStore


class StateStoreEdgeCaseTests(unittest.TestCase):
    def test_corrupt_json_fails_loudly(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "state.json"
            path.write_text("{broken", encoding="utf-8")
            with self.assertRaisesRegex(RuntimeError, "Unable to load renewal state"):
                StateStore(str(path))

    def test_old_schema_is_migrated_without_losing_hosts(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "state.json"
            path.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "hosts": {"example.ddns.net": {"active": True}},
                    }
                )
            )
            state = StateStore(str(path)).state
            self.assertEqual(state["schema_version"], 4)
            self.assertIn("example.ddns.net", state["hosts"])
            self.assertFalse(state["dry_run"])
            self.assertEqual(state["would_renew"], [])
            self.assertFalse(state["notifications"]["enabled"])
            self.assertEqual(state["retry"]["consecutive_failures"], 0)
            self.assertIsNone(state["retry"]["next_retry"])

    def test_failed_atomic_replace_preserves_previous_file(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "state.json"
            store = StateStore(str(path))
            store.record_next_check("first")
            before = path.read_text(encoding="utf-8")
            store.state["next_check"] = "second"

            with patch("state_store.os.replace", side_effect=OSError("disk error")):
                with self.assertRaisesRegex(OSError, "disk error"):
                    store.save()

            self.assertEqual(path.read_text(encoding="utf-8"), before)
            self.assertEqual(list(Path(directory).glob(".state-*.json")), [])

    def test_new_run_clears_previous_dry_run_preview(self):
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, "state.json")
            store = StateStore(path)
            store.record_run_started(dry_run=True)
            store.record_would_renew(["example.ddns.net"])
            store.record_run_started(dry_run=False)
            self.assertFalse(store.state["dry_run"])
            self.assertEqual(store.state["would_renew"], [])

    def test_inventory_preserves_verified_renewal_metadata(self):
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, "state.json")
            store = StateStore(path)
            store.record_host(
                "example.ddns.net",
                "old",
                "new",
                {"active": True, "host_id": "123"},
            )
            store.record_inventory(
                {
                    "example.ddns.net": {
                        "active": True,
                        "host_id": "123",
                        "data_update": "new",
                    }
                }
            )
            host = store.state["hosts"]["example.ddns.net"]
            self.assertEqual(host["previous_data_update"], "old")
            self.assertIn("last_verified_renewal", host)

    def test_stale_instances_merge_independent_updates(self):
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, "state.json")
            scheduler_store = StateStore(path)
            notification_store = StateStore(path)

            scheduler_store.record_next_check("2026-09-23T12:00:00+00:00")
            notification_store.record_notification_success()

            state = StateStore(path).state
            self.assertEqual(state["next_check"], "2026-09-23T12:00:00+00:00")
            self.assertIsNotNone(state["notifications"]["last_success"])


if __name__ == "__main__":
    unittest.main()
