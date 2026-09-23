import ast
import pathlib
import unittest


ROOT = pathlib.Path(__file__).parents[1]


class CodeQualityConfigTests(unittest.TestCase):
    def test_development_tools_are_configured(self):
        requirements = (ROOT / "requirements-dev.txt").read_text(encoding="utf-8")
        self.assertIn("ruff", requirements)
        self.assertIn("mypy", requirements)
        self.assertIn("pre-commit", requirements)

    def test_precommit_runs_lint_format_and_types(self):
        config = (ROOT / ".pre-commit-config.yaml").read_text(encoding="utf-8")
        self.assertIn("ruff check", config)
        self.assertIn("ruff format --check", config)
        self.assertIn("entry: mypy", config)

    def test_global_settings_dictionary_was_removed(self):
        self.assertFalse((ROOT / "settings.py").exists())
        source = (ROOT / "app_config.py").read_text(encoding="utf-8")
        self.assertIn("@dataclass(frozen=True, slots=True)", source)

    def test_obsolete_packages_were_removed(self):
        for package in ("logger", "simpleTable"):
            with self.subTest(package=package):
                self.assertFalse((ROOT / package).exists())

    def test_obsolete_flask_template_was_removed(self):
        self.assertFalse((ROOT / "flask_template.py").exists())
        self.assertTrue((ROOT / "status_server.py").exists())

    def test_status_server_has_no_mutable_module_state(self):
        source = (ROOT / "status_server.py").read_text(encoding="utf-8")
        tree = ast.parse(source)
        forbidden = (ast.Global, ast.AsyncFunctionDef)
        self.assertFalse(any(isinstance(node, forbidden) for node in ast.walk(tree)))
        self.assertNotIn(
            "flask.Flask(__name__)\n", source.split("class StatusServer:")[0]
        )

    def test_mypy_covers_operational_core(self):
        config = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
        for module in (
            "noip_bot.py",
            "noip_renew/noip_renew.py",
            "noip_renew/page_contract.py",
            "run_lock.py",
            "state_store.py",
            "status_server.py",
        ):
            with self.subTest(module=module):
                self.assertIn(f'"{module}"', config)


if __name__ == "__main__":
    unittest.main()
