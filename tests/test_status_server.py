import os
import unittest
from unittest.mock import patch

import status_server


STATUS_TOKEN = "test-status-token-that-is-at-least-32-characters"


class FakeStateStore:
    state = {
        "last_run": "2026-09-23T00:00:00+00:00",
        "last_success": "2026-09-23T00:01:00+00:00",
        "last_error": {
            "timestamp": "2026-09-23T00:02:00+00:00",
            "type": "RuntimeError",
            "message": "secret upstream failure details",
        },
        "next_check": "2099-09-24T00:00:00+00:00",
        "notifications": {
            "enabled": True,
            "last_success": None,
            "last_error": {
                "timestamp": "2026-09-23T00:02:00+00:00",
                "type": "OSError",
                "message": "secret notification failure details",
            },
        },
        "hosts": {
            "example.ddns.net": {
                "host_id": "123456",
                "active": True,
                "data_update": "Sep 23, 2026 00:00:00",
            }
        },
    }


class StatusServerSecurityTests(unittest.TestCase):
    def setUp(self):
        self.client = status_server.app.test_client()

    def request_status(self, token=STATUS_TOKEN):
        return self.client.get(
            "/status.json", headers={"Authorization": f"Bearer {token}"}
        )

    @patch.object(status_server, "StateStore", FakeStateStore)
    def test_health_is_unauthenticated_and_minimal(self):
        with patch.dict(os.environ, {"STATUS_TOKEN": STATUS_TOKEN}):
            response = self.client.get("/health")

        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.get_json(), {"status": "unhealthy", "healthy": False})
        self.assertEqual(response.headers["Cache-Control"], "no-store")

    @patch.object(status_server, "StateStore", FakeStateStore)
    def test_detailed_status_requires_bearer_token(self):
        with patch.dict(os.environ, {"STATUS_TOKEN": STATUS_TOKEN}):
            missing = self.client.get("/status.json")
            incorrect = self.request_status("incorrect-token-that-is-still-long-enough")

        self.assertEqual(missing.status_code, 401)
        self.assertEqual(incorrect.status_code, 401)
        self.assertEqual(missing.headers["WWW-Authenticate"], "Bearer")

    @patch.object(status_server, "StateStore", FakeStateStore)
    def test_short_or_missing_token_disables_detailed_status(self):
        with patch.dict(os.environ, {"STATUS_TOKEN": "short"}):
            response = self.request_status("short")

        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.get_json()["status"], "unavailable")

    @patch.object(status_server, "StateStore", FakeStateStore)
    def test_authorized_status_redacts_sensitive_details(self):
        with patch.dict(os.environ, {"STATUS_TOKEN": STATUS_TOKEN}):
            response = self.request_status()

        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertNotIn("message", payload["last_error"])
        self.assertNotIn("message", payload["notifications"]["last_error"])
        self.assertNotIn("host_id", payload["hosts"]["example.ddns.net"])
        self.assertNotIn("secret upstream failure details", payload["reasons"])

    def test_root_status_page_is_also_protected(self):
        with patch.dict(os.environ, {"STATUS_TOKEN": STATUS_TOKEN}):
            unauthorized = self.client.get("/")
            authorized = self.client.get(
                "/", headers={"Authorization": f"Bearer {STATUS_TOKEN}"}
            )

        self.assertEqual(unauthorized.status_code, 401)
        self.assertEqual(authorized.status_code, 200)


if __name__ == "__main__":
    unittest.main()
