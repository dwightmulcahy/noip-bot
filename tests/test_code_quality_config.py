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


if __name__ == "__main__":
    unittest.main()
