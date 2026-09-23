import pathlib
import unittest


ROOT = pathlib.Path(__file__).parents[1]


class ContainerBrowserConfigTests(unittest.TestCase):
    def test_docker_enables_headless_chromium(self):
        dockerfile = (ROOT / "Dockerfile").read_text(encoding="utf-8")
        self.assertIn("HEADLESS=true", dockerfile)
        self.assertIn("CHROMEDRIVER_BIN=/usr/bin/chromedriver", dockerfile)

    def test_browser_has_required_container_flags(self):
        source = (ROOT / "noip_renew" / "noip_renew.py").read_text(encoding="utf-8")
        self.assertIn('"--headless=new"', source)
        self.assertIn('"--disable-dev-shm-usage"', source)
        self.assertIn('"--remote-debugging-pipe"', source)

    def test_error_email_converts_exception_to_text(self):
        source = (ROOT / "notifications.py").read_text(encoding="utf-8")
        self.assertIn("sendEmail(send_to, subject, str(body))", source)


if __name__ == "__main__":
    unittest.main()
