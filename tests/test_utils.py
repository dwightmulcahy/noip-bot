import socket
import unittest

from utils import UpTime, findFreePort, getMyIpAddr


class UtilsTests(unittest.TestCase):
    def test_package_exports_resolve(self):
        self.assertTrue(callable(getMyIpAddr))
        self.assertTrue(callable(findFreePort))
        self.assertTrue(callable(UpTime))

    def test_find_free_port_returns_bindable_port(self):
        port = findFreePort()
        listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            listener.bind(("127.0.0.1", port))
        finally:
            listener.close()

    def test_uptime_format(self):
        ticks = iter((100.0, 3761.0))
        uptime = UpTime(clock=lambda: next(ticks))
        self.assertEqual(str(uptime), "1h 1m 1s")


if __name__ == "__main__":
    unittest.main()
