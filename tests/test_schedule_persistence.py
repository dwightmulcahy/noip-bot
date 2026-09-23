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
            if isinstance(node, ast.FunctionDef) and node.name == "update_hosts"
        )
        calls = [
            node
            for node in ast.walk(update_hosts)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "record_next_check"
        ]
        self.assertEqual(
            len(calls),
            2,
            "Both the retry schedule and successful schedule must be persisted",
        )


if __name__ == "__main__":
    unittest.main()
