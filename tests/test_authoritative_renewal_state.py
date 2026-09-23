import pathlib
import unittest


class AuthoritativeRenewalStateTests(unittest.TestCase):
    def test_renewal_does_not_fabricate_thirty_day_expiration(self):
        source = (
            pathlib.Path(__file__).parents[1] / "noip_renew" / "noip_renew.py"
        ).read_text(encoding="utf-8")
        self.assertNotIn("(expires_in or 0) + 30", source)
        self.assertIn(
            "refreshed_host = self.get_host_inventory().get(host_name)", source
        )


if __name__ == "__main__":
    unittest.main()
