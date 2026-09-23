import unittest
from dataclasses import FrozenInstanceError

from app_config import AppConfig


class FakeScheduler:
    def add_job(self, function, trigger, **kwargs):
        return None

    def shutdown(self):
        return None


def make_config(**overrides):
    values = {
        "noip_id": "user@example.com",
        "noip_password": "secret",
        "bind_address": "127.0.0.1",
        "port": 8080,
        "timezone": "UTC",
        "max_check_interval_days": 5,
        "scheduler": FakeScheduler(),
    }
    values.update(overrides)
    return AppConfig(**values)


class AppConfigTests(unittest.TestCase):
    def test_configuration_is_immutable(self):
        config = make_config()
        with self.assertRaises(FrozenInstanceError):
            config.port = 9090

    def test_instances_do_not_share_state(self):
        first = make_config(noip_id="first@example.com")
        second = make_config(noip_id="second@example.com")
        self.assertEqual(first.noip_id, "first@example.com")
        self.assertEqual(second.noip_id, "second@example.com")

    def test_invalid_port_interval_and_timezone_are_rejected(self):
        with self.assertRaisesRegex(ValueError, "port"):
            make_config(port=0)
        with self.assertRaisesRegex(ValueError, "max_check_interval_days"):
            make_config(max_check_interval_days=0)
        with self.assertRaisesRegex(ValueError, "timezone"):
            make_config(timezone="Not/A-Timezone")

    def test_credentials_are_required_for_real_runs(self):
        with self.assertRaisesRegex(ValueError, "NOIP_ID"):
            make_config(noip_id="", noip_password="")
        config = make_config(noip_id="", noip_password="", skip_initial_run=True)
        self.assertTrue(config.skip_initial_run)


if __name__ == "__main__":
    unittest.main()
