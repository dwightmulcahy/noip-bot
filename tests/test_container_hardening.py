import pathlib
import re
import unittest


ROOT = pathlib.Path(__file__).parents[1]


class ContainerHardeningTests(unittest.TestCase):
    def test_base_image_is_versioned_and_digest_pinned(self):
        dockerfile = (ROOT / "Dockerfile").read_text(encoding="utf-8")
        first_line = dockerfile.splitlines()[0]
        self.assertRegex(
            first_line,
            r"^FROM python:3\.14\.\d+-slim-bookworm@sha256:[0-9a-f]{64}$",
        )

    def test_image_runs_as_fixed_non_root_user(self):
        dockerfile = (ROOT / "Dockerfile").read_text(encoding="utf-8")
        self.assertIn("USER 10001:10001", dockerfile)
        self.assertIn("COPY --chown=noipbot:noipbot . .", dockerfile)
        self.assertIn("PYTHONDONTWRITEBYTECODE=1", dockerfile)

    def test_compose_applies_runtime_restrictions(self):
        compose = (ROOT / "docker-compose.yml").read_text(encoding="utf-8")
        required = (
            "init: true",
            "read_only: true",
            'user: "10001:10001"',
            "cap_drop:\n      - ALL",
            "no-new-privileges:true",
            "pids_limit: 256",
            "mem_limit: 1g",
            "shm_size: 256m",
            "stop_signal: SIGINT",
            "/tmp:rw,noexec,nosuid,nodev",
            "/home/noipbot:rw,noexec,nosuid,nodev",
        )
        for setting in required:
            with self.subTest(setting=setting):
                self.assertIn(setting, compose)

    def test_compose_rotates_container_logs(self):
        for filename in ("docker-compose.yml", "compose.qnap.yaml"):
            compose = (ROOT / filename).read_text(encoding="utf-8")
            with self.subTest(filename=filename):
                self.assertIn("driver: json-file", compose)
                self.assertIn('max-size: "10m"', compose)
                self.assertIn('max-file: "3"', compose)

    def test_qnap_compose_pulls_hardened_published_image(self):
        compose = (ROOT / "compose.qnap.yaml").read_text(encoding="utf-8")
        self.assertIn("image: ${IMAGE:-dwightmulcahy/noip-bot:latest}", compose)
        self.assertNotIn("build:", compose)
        self.assertIn('"${HOST_PORT:-9181}:8080"', compose)
        self.assertIn(
            "${QNAP_DATA_DIR:-/share/Container/noip-bot/data}:/app/data",
            compose,
        )
        for setting in (
            "read_only: true",
            'user: "10001:10001"',
            "cap_drop:\n      - ALL",
            "no-new-privileges:true",
        ):
            with self.subTest(setting=setting):
                self.assertIn(setting, compose)

    def test_smoke_test_uses_production_security_restrictions(self):
        script = (ROOT / "scripts" / "container_smoke_test.sh").read_text(
            encoding="utf-8"
        )
        for flag in (
            "--read-only",
            "--user 10001:10001",
            "--cap-drop ALL",
            "--security-opt no-new-privileges:true",
            "--pids-limit 256",
            "--memory 1g",
        ):
            with self.subTest(flag=flag):
                self.assertIn(flag, script)

    def test_dockerfile_contains_no_mutable_latest_reference(self):
        dockerfile = (ROOT / "Dockerfile").read_text(encoding="utf-8")
        self.assertIsNone(re.search(r"^FROM\s+\S+:latest", dockerfile, re.MULTILINE))

    def test_pcre2_security_update_and_floor_are_enforced(self):
        dockerfile = (ROOT / "Dockerfile").read_text(encoding="utf-8")
        self.assertIn("libpcre2-8-0", dockerfile)
        self.assertIn('ge "10.42-1+deb12u1"', dockerfile)
        self.assertIn("dpkg --compare-versions", dockerfile)


if __name__ == "__main__":
    unittest.main()
