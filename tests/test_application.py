import os
import tempfile
import unittest
from unittest.mock import Mock, patch

from app_config import AppConfig
from application import NoIpApplication


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


if __name__ == "__main__":
    unittest.main()
