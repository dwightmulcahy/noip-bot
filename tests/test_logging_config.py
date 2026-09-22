import json
import logging
import unittest

from logging_config import JsonFormatter


class JsonFormatterTests(unittest.TestCase):
    def test_log_line_is_json_with_context(self):
        record = logging.LogRecord(
            "test", logging.INFO, __file__, 1, "renewed", (), None
        )
        record.event = "renewal_verified"
        record.host = "example.ddns.net"
        payload = json.loads(JsonFormatter().format(record))

        self.assertEqual(payload["level"], "INFO")
        self.assertEqual(payload["event"], "renewal_verified")
        self.assertEqual(payload["host"], "example.ddns.net")


if __name__ == "__main__":
    unittest.main()
