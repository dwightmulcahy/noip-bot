import pathlib
import unittest


ROOT = pathlib.Path(__file__).parents[1]


class SecurityConstraintTests(unittest.TestCase):
    def test_known_vulnerable_versions_have_security_floors(self):
        constraints = (ROOT / "constraints.txt").read_text(encoding="utf-8")
        self.assertIn("msgpack>=1.2.1", constraints)
        self.assertIn("setuptools>=78.1.1", constraints)

    def test_container_installs_secured_setuptools(self):
        dockerfile = (ROOT / "Dockerfile").read_text(encoding="utf-8")
        self.assertIn('"setuptools>=78.1.1"', dockerfile)
        self.assertIn("COPY requirements.txt constraints.txt ./", dockerfile)

    def test_trivy_jobs_only_run_vulnerability_scanner(self):
        for path in (ROOT / ".github" / "workflows").glob("*.yml"):
            workflow = path.read_text(encoding="utf-8")
            if "aquasecurity/trivy-action@" in workflow:
                self.assertIn("scanners: vuln", workflow)


if __name__ == "__main__":
    unittest.main()
