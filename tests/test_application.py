import os
import tempfile
import unittest
from datetime import datetime
from unittest.mock import Mock, patch

from app_config import AppConfig
from application import NoIpApplication
from state_store import StateStore


class FakeScheduler:
    def __init__(self):
        self.jobs = []

    def add_job(self, function, trigger, **kwargs):
        self.jobs.append((function, trigger, kwargs))

    def shutdown(self):
        return None


class ApplicationTests(unittest.TestCase):
    def test_skip_initial_run_starts_server_without_creating_robot(self):
        with tempfile.TemporaryDirectory() as directory:
            state_path = os.path.join(directory, "state.json")
            scheduler = FakeScheduler()
            config = AppConfig(
                noip_id="",
                noip_password="",
                bind_address="127.0.0.1",
                port=8080,
                timezone="UTC",
                max_check_interval_days=5,
                scheduler=scheduler,
                skip_initial_run=True,
            )
            robot_factory = Mock(side_effect=AssertionError("robot must not start"))
            application = NoIpApplication(config, robot_factory=robot_factory)

            with (
                patch.dict(os.environ, {"STATE_FILE": state_path}),
                patch.object(application, "send_email", return_value=False),
                patch("application.startWebServer") as start_server,
            ):
                application.run()

            robot_factory.assert_not_called()
            self.assertEqual(scheduler.jobs, [])
            start_server.assert_called_once_with(
                "noip_bot", bind="127.0.0.1", port=8080
            )

    def test_failure_schedules_escalating_retry_and_sends_first_alert(self):
        with tempfile.TemporaryDirectory() as directory:
            state_path = os.path.join(directory, "state.json")
            scheduler = FakeScheduler()
            config = AppConfig(
                noip_id="user@example.com",
                noip_password="secret",
                bind_address="127.0.0.1",
                port=8080,
                timezone="UTC",
                max_check_interval_days=5,
                scheduler=scheduler,
            )
            application = NoIpApplication(
                config,
                robot_factory=Mock(side_effect=RuntimeError("navigation failed")),
            )

            with (
                patch.dict(os.environ, {"STATE_FILE": state_path}),
                patch("application.uniform", return_value=0),
                patch.object(
                    application, "send_email", return_value=True
                ) as send_email,
            ):
                before = datetime.now().astimezone()
                with self.assertRaisesRegex(RuntimeError, "navigation failed"):
                    application.update_hosts()
                after = datetime.now().astimezone()

            self.assertEqual(len(scheduler.jobs), 1)
            retry_at = scheduler.jobs[0][2]["run_date"]
            self.assertGreaterEqual((retry_at - before).total_seconds(), 899)
            self.assertLessEqual((retry_at - after).total_seconds(), 901)
            state = StateStore(state_path).state
            self.assertEqual(state["retry"]["consecutive_failures"], 1)
            self.assertEqual(state["retry"]["next_retry"], retry_at.isoformat())
            send_email.assert_called_once()
            self.assertEqual(send_email.call_args.args[1], "NOIP-Bot renewal failure")


if __name__ == "__main__":
    unittest.main()
