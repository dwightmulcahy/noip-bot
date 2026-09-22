import os
import unittest
from unittest.mock import patch

from version import get_version, normalize_version


class VersionTests(unittest.TestCase):
    def test_normalizes_optional_v_prefix(self):
        self.assertEqual(normalize_version("v0.2.3"), "0.2.3")
        self.assertEqual(normalize_version("0.2.3"), "0.2.3")

    def test_environment_version_takes_precedence(self):
        with patch.dict(os.environ, {"APP_VERSION": "v0.2.3"}):
            self.assertEqual(get_version(), "0.2.3")

    def test_git_tag_is_used_without_environment_override(self):
        completed = type("Result", (), {"stdout": "v1.2.3\n"})()
        with patch.dict(os.environ, {}, clear=True):
            with patch("version.subprocess.run", return_value=completed):
                self.assertEqual(get_version(), "1.2.3")

    def test_development_fallback_when_git_is_unavailable(self):
        with patch.dict(os.environ, {}, clear=True):
            with patch("version.subprocess.run", side_effect=FileNotFoundError):
                self.assertEqual(get_version(), "0.0.0-dev")


if __name__ == "__main__":
    unittest.main()
