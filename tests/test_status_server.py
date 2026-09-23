import os
import unittest
from unittest.mock import patch

from status_server import StatusServer


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
        self.sent_messages = []

        def send_message(recipient, subject, body):
            self.sent_messages.append((recipient, subject, body))
            return True

        self.server = StatusServer(
            "test-noip-bot",
            FakeStateStore,
            otp_sender=send_message,
            otp_recipient="owner@example.com",
        )
        self.client = self.server.app.test_client()

    def request_status(self, token=STATUS_TOKEN):
        return self.client.get(
            "/status.json", headers={"Authorization": f"Bearer {token}"}
        )

    def csrf_token(self):
        with self.client.session_transaction() as session:
            return session["csrf_token"]

    def test_health_is_unauthenticated_and_minimal(self):
        with patch.dict(os.environ, {"STATUS_TOKEN": STATUS_TOKEN}):
            response = self.client.get("/health")

        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.get_json(), {"status": "unhealthy", "healthy": False})
        self.assertEqual(response.headers["Cache-Control"], "no-store")

    def test_detailed_status_requires_bearer_token(self):
        with patch.dict(os.environ, {"STATUS_TOKEN": STATUS_TOKEN}):
            missing = self.client.get("/status.json")
            incorrect = self.request_status("incorrect-token-that-is-still-long-enough")

        self.assertEqual(missing.status_code, 401)
        self.assertEqual(incorrect.status_code, 401)
        self.assertEqual(missing.headers["WWW-Authenticate"], "Bearer")

    def test_short_or_missing_token_disables_detailed_status(self):
        with patch.dict(os.environ, {"STATUS_TOKEN": "short"}):
            response = self.request_status("short")

        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.get_json()["status"], "unavailable")

    def test_authorized_status_redacts_sensitive_details(self):
        with patch.dict(os.environ, {"STATUS_TOKEN": STATUS_TOKEN}):
            response = self.request_status()

        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertNotIn("message", payload["last_error"])
        self.assertNotIn("message", payload["notifications"]["last_error"])
        self.assertNotIn("host_id", payload["hosts"]["example.ddns.net"])
        self.assertNotIn("secret upstream failure details", payload["reasons"])

    def test_root_status_page_redirects_to_login_and_accepts_bearer_token(self):
        with patch.dict(os.environ, {"STATUS_TOKEN": STATUS_TOKEN}):
            unauthorized = self.client.get("/")
            authorized = self.client.get(
                "/", headers={"Authorization": f"Bearer {STATUS_TOKEN}"}
            )

        self.assertEqual(unauthorized.status_code, 302)
        self.assertEqual(unauthorized.headers["Location"], "/login")
        self.assertEqual(authorized.status_code, 200)
        self.assertIn(b"Managed records", authorized.data)
        self.assertIn(b"example.ddns.net", authorized.data)
        self.assertNotIn(b"secret upstream failure details", authorized.data)

    def test_email_code_login_creates_session_and_logout_clears_it(self):
        with (
            patch.dict(os.environ, {"STATUS_TOKEN": STATUS_TOKEN}),
            patch("status_server.secrets.randbelow", return_value=123456),
        ):
            self.client.get("/login")
            csrf_token = self.csrf_token()
            sent = self.client.post("/login/send", data={"csrf_token": csrf_token})
            rejected = self.client.post(
                "/login/verify",
                data={"code": "000000", "csrf_token": csrf_token},
            )
            accepted = self.client.post(
                "/login/verify",
                data={"code": "123456", "csrf_token": csrf_token},
                follow_redirects=True,
            )
            logged_out = self.client.post(
                "/logout",
                data={"csrf_token": self.csrf_token()},
                follow_redirects=False,
            )
            protected_again = self.client.get("/")

        self.assertEqual(sent.status_code, 200)
        self.assertEqual(len(self.sent_messages), 1)
        self.assertEqual(self.sent_messages[0][0], "owner@example.com")
        self.assertIn("123456", self.sent_messages[0][2])
        self.assertEqual(rejected.status_code, 401)
        self.assertIn(b"incorrect", rejected.data)
        self.assertEqual(accepted.status_code, 200)
        self.assertIn(b"No-IP renewal service", accepted.data)
        self.assertEqual(logged_out.status_code, 302)
        self.assertEqual(protected_again.status_code, 302)

    def test_login_code_is_single_use_and_send_is_rate_limited(self):
        with (
            patch.dict(os.environ, {"STATUS_TOKEN": STATUS_TOKEN}),
            patch("status_server.secrets.randbelow", return_value=654321),
        ):
            self.client.get("/login")
            csrf_token = self.csrf_token()
            first_send = self.client.post(
                "/login/send", data={"csrf_token": csrf_token}
            )
            second_send = self.client.post(
                "/login/send", data={"csrf_token": csrf_token}
            )
            accepted = self.client.post(
                "/login/verify",
                data={"code": "654321", "csrf_token": csrf_token},
            )
            self.client.post("/logout", data={"csrf_token": self.csrf_token()})
            self.client.get("/login")
            reused = self.client.post(
                "/login/verify",
                data={"code": "654321", "csrf_token": self.csrf_token()},
            )

        self.assertEqual(first_send.status_code, 200)
        self.assertEqual(second_send.status_code, 429)
        self.assertEqual(accepted.status_code, 302)
        self.assertEqual(reused.status_code, 401)

    def test_login_is_disabled_without_email_sender(self):
        server = StatusServer(
            "test-noip-bot",
            FakeStateStore,
            otp_recipient="owner@example.com",
        )
        with patch.dict(os.environ, {"STATUS_TOKEN": STATUS_TOKEN}):
            response = server.app.test_client().get("/login")

        self.assertEqual(response.status_code, 503)
        self.assertIn(b"Email login is unavailable", response.data)

    def test_dashboard_distinguishes_configured_and_last_run_modes(self):
        with patch.dict(
            os.environ,
            {"STATUS_TOKEN": STATUS_TOKEN, "DRY_RUN": "false"},
        ):
            response = self.client.get(
                "/", headers={"Authorization": f"Bearer {STATUS_TOKEN}"}
            )
            payload = self.request_status().get_json()

        self.assertIn(b"Live renewal", response.data)
        self.assertFalse(payload["configured_dry_run"])

    def test_security_headers_are_applied_to_dashboard(self):
        with patch.dict(os.environ, {"STATUS_TOKEN": STATUS_TOKEN}):
            response = self.client.get("/login")

        self.assertEqual(response.headers["X-Frame-Options"], "DENY")
        self.assertEqual(response.headers["X-Content-Type-Options"], "nosniff")
        self.assertIn("default-src 'none'", response.headers["Content-Security-Policy"])

    def test_server_instances_do_not_share_page_state(self):
        first = StatusServer("first", FakeStateStore)
        second = StatusServer("second", FakeStateStore)
        first.set_page_message("first message")
        second.set_page_message("second message")

        self.assertEqual(first.get_page_message(), "first message")
        self.assertEqual(second.get_page_message(), "second message")


if __name__ == "__main__":
    unittest.main()
