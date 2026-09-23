import pathlib
import unittest
from unittest.mock import patch

from scripts.verify_package_security import numeric_version, verify_security_floors


ROOT = pathlib.Path(__file__).parents[1]


class SecurityScanningTests(unittest.TestCase):
    def test_version_parser_handles_release_suffix(self):
        self.assertEqual(numeric_version("78.1.1.post1"), (78, 1, 1))

    def test_vulnerable_installed_package_fails(self):
        with patch("scripts.verify_package_security.version", return_value="1.1.2"):
            with self.assertRaisesRegex(RuntimeError, "security floor"):
                verify_security_floors()

    def test_trivy_skips_only_pip_embedded_sbom(self):
        for path in (ROOT / ".github" / "workflows").glob("*.yml"):
            workflow = path.read_text(encoding="utf-8")
            if "aquasecurity/trivy-action@" in workflow:
                self.assertIn(
                    'skip-files: "**/site-packages/pip/_vendor/bom.cdx.json"',
                    workflow,
                )
                self.assertIn("verify_package_security.py", workflow)


if __name__ == "__main__":
    unittest.main()
