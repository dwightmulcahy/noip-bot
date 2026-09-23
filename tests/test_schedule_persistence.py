import ast
import pathlib
import unittest


class SchedulePersistenceTests(unittest.TestCase):
    def test_success_and_retry_schedules_are_persisted(self):
        source_path = pathlib.Path(__file__).parents[1] / "application.py"
        tree = ast.parse(source_path.read_text(encoding="utf-8"))
        update_hosts = next(
            node
            for node in ast.walk(tree)
            if isinstance(node, ast.FunctionDef) and node.name == "_update_hosts_locked"
        )
        persisted_methods = [
            node.func.attr
            for node in ast.walk(update_hosts)
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
        ]
        next_check_calls = [
            node
            for node in ast.walk(update_hosts)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "record_next_check"
        ]
        self.assertEqual(
            len(next_check_calls),
            1,
            "The successful schedule must be persisted",
        )
        self.assertIn("record_retry_scheduled", persisted_methods)


if __name__ == "__main__":
    unittest.main()
