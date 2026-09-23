import ast
import os
import tempfile
import unittest

from state_store import StateStore


class DryRunTests(unittest.TestCase):
    def test_state_records_dry_run_and_would_renew(self):
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, "state.json")
            store = StateStore(path)
            store.record_run_started(dry_run=True)
            store.record_would_renew(["example.ddns.net"])
            reloaded = StateStore(path).state
            self.assertTrue(reloaded["dry_run"])
            self.assertEqual(reloaded["would_renew"], ["example.ddns.net"])
            self.assertEqual(reloaded["schema_version"], 3)

    def test_dry_run_branch_skips_click_path(self):
        source_path = (
            __import__("pathlib").Path(__file__).parents[1]
            / "noip_renew"
            / "noip_renew.py"
        )
        tree = ast.parse(source_path.read_text(encoding="utf-8"))
        update_hosts = next(
            node
            for node in ast.walk(tree)
            if isinstance(node, ast.FunctionDef) and node.name == "update_hosts"
        )
        dry_run_if = next(
            node
            for node in ast.walk(update_hosts)
            if isinstance(node, ast.If)
            and isinstance(node.test, ast.Attribute)
            and node.test.attr == "dry_run"
        )
        self.assertTrue(any(isinstance(node, ast.Continue) for node in dry_run_if.body))
        self.assertFalse(
            any(
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr == "update_host"
                for node in ast.walk(dry_run_if)
            )
        )

    def test_dry_run_bypasses_restored_schedule(self):
        source_path = __import__("pathlib").Path(__file__).parents[1] / "application.py"
        source = source_path.read_text(encoding="utf-8")
        self.assertIn("elif restored_check and not self.config.dry_run:", source)

    def test_smoke_mode_skips_initial_renewal(self):
        root = __import__("pathlib").Path(__file__).parents[1]
        cli_source = (root / "noip_bot.py").read_text(encoding="utf-8")
        application_source = (root / "application.py").read_text(encoding="utf-8")
        self.assertIn('envvar="SKIP_INITIAL_RUN"', cli_source)
        self.assertIn("if self.config.skip_initial_run:", application_source)


if __name__ == "__main__":
    unittest.main()
