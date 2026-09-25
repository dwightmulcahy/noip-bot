import unittest
from pathlib import Path

from noip_renew.page_contract import (
    PageContractError,
    assert_login_contract,
    assert_verification_contract,
    parse_host_contract,
)


FIXTURES = Path(__file__).parent / "fixtures" / "noip"


def fixture(name):
    return (FIXTURES / name).read_text(encoding="utf-8")


class HtmlContractTests(unittest.TestCase):
    def test_status_dashboard_is_semantic_html_not_raw_markdown(self):
        template = (
            Path(__file__).parents[1] / "templates" / "status_dashboard.html"
        ).read_text(encoding="utf-8")

        self.assertIn('<section class="summary-grid"', template)
        self.assertIn("<table>", template)
        self.assertIn("configured_dry_run", template)
        self.assertIn("v{{ app_version }}", template)
        self.assertNotIn("**Host Name**", template)

    def test_login_page_contract(self):
        assert_login_contract(fixture("login.html"))

    def test_verification_page_requires_exactly_six_otp_inputs(self):
        assert_verification_contract(fixture("verification.html"))
        broken = fixture("verification.html").replace(
            '<input inputmode="numeric" maxlength="1">', "", 1
        )
        with self.assertRaisesRegex(PageContractError, "expected 6 OTP inputs"):
            assert_verification_contract(broken)

    def test_host_inventory_contract_extracts_authoritative_fields(self):
        hosts = parse_host_contract(fixture("hosts.html"))

        self.assertEqual(
            [host.hostname for host in hosts],
            ["alpha.example.test", "beta.example.test"],
        )
        self.assertEqual(hosts[0].host_id, "100001")
        self.assertEqual(hosts[0].data_update, "Sep 17, 2026 13:38:34")
        self.assertEqual(hosts[0].expires_in_days, 5)
        self.assertTrue(hosts[0].renewal_available)
        self.assertIsNone(hosts[1].expires_in_days)
        self.assertFalse(hosts[1].renewal_available)

    def test_verified_renewal_contract_changes_timestamp_and_removes_control(self):
        before = {
            host.host_id: host for host in parse_host_contract(fixture("hosts.html"))
        }
        after = {
            host.host_id: host for host in parse_host_contract(fixture("renewed.html"))
        }

        self.assertNotEqual(before["100001"].data_update, after["100001"].data_update)
        self.assertTrue(before["100001"].renewal_available)
        self.assertFalse(after["100001"].renewal_available)

    def test_interstitial_fails_login_and_hosts_contracts(self):
        html = fixture("interstitial.html")
        with self.assertRaises(PageContractError):
            assert_login_contract(html)
        with self.assertRaises(PageContractError):
            parse_host_contract(html)

    def test_incomplete_host_row_fails_contract(self):
        html = fixture("hosts.html").replace(
            ' data-update="Sep 17, 2026 13:38:34"', "", 1
        )
        with self.assertRaisesRegex(PageContractError, "data_update"):
            parse_host_contract(html)


if __name__ == "__main__":
    unittest.main()
