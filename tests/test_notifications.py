import logging
import os
import tempfile
import unittest

from notifications import send_notification
from state_store import StateStore


class FakeServer:
    def __init__(self, result=True, error=None):
        self.result = result
        self.error = error
        self.calls = []

    def sendEmail(self, send_to, subject, body):
        self.calls.append((send_to, subject, body))
        if self.error:
            raise self.error
        return self.result


class NotificationTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.path = os.path.join(self.directory.name, "state.json")
        self.store = StateStore(self.path)
        self.logger = logging.getLogger("test.notifications")

    def send(self, server):
        return send_notification(
            server, "user@example.com", "subject", RuntimeError("body"),
            self.store, self.logger,
        )

    def test_success_is_persisted_and_body_is_text(self):
        server = FakeServer()
        self.assertTrue(self.send(server))
        state = StateStore(self.path).state["notifications"]
        self.assertTrue(state["enabled"])
        self.assertIsNotNone(state["last_attempt"])
        self.assertEqual(state["last_attempt"], state["last_success"])
        self.assertIsNone(state["last_error"])
        self.assertEqual(server.calls[0][2], "body")

    def test_false_provider_response_is_captured(self):
        self.assertFalse(self.send(FakeServer(result=False)))
        error = StateStore(self.path).state["notifications"]["last_error"]
        self.assertEqual(error["type"], "NotificationDeliveryError")

    def test_provider_exception_never_escapes(self):
        self.assertFalse(self.send(FakeServer(error=TimeoutError("timed out"))))
        error = StateStore(self.path).state["notifications"]["last_error"]
        self.assertEqual(error["type"], "TimeoutError")
        self.assertEqual(error["message"], "timed out")

    def test_success_clears_previous_failure(self):
        self.send(FakeServer(error=OSError("offline")))
        self.assertTrue(self.send(FakeServer()))
        self.assertIsNone(
            StateStore(self.path).state["notifications"]["last_error"]
        )

    def test_missing_server_is_disabled_not_failed(self):
        self.assertFalse(self.send(None))
        state = StateStore(self.path).state["notifications"]
        self.assertFalse(state["enabled"])
        self.assertIsNone(state["last_error"])

    def test_missing_state_store_does_not_block_delivery(self):
        server = FakeServer()
        self.assertTrue(send_notification(
            server, "user@example.com", "subject", "body", None, self.logger
        ))


if __name__ == "__main__":
    unittest.main()
