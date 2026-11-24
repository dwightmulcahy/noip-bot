import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import whats_new
from status_server import StatusServer
from tests.test_status_server import STATUS_TOKEN, FakeStateStore

NOTES = {
    "current": "1.3.0",
    "releases": [
        {
            "version": "1.3.0",
            "date": "2026-11-24",
            "internal": 2,
            "sections": [
                {
                    "type": "breaking",
                    "title": "Breaking changes",
                    "items": [{"text": "STATUS_TOKEN is required"}],
                },
                {
                    "type": "feat",
                    "title": "Features",
                    "items": [{"text": "<b>renew</b> earlier"}],
                },
            ],
        },
        {"version": "1.2.1", "date": "2026-11-20", "internal": 1, "sections": []},
        {
            "version": "1.2.0",
            "date": "2026-11-01",
            "internal": 0,
            "sections": [
                {"type": "fix", "title": "Bug fixes", "items": [{"text": "old fix"}]}
            ],
        },
    ],
}
AUTH = {"Authorization": f"Bearer {STATUS_TOKEN}"}


class PanelLogicTests(unittest.TestCase):
    def test_load_missing_or_bad_file_is_empty(self):
        with tempfile.TemporaryDirectory() as d:
            bad = Path(d) / "c.json"
            self.assertEqual(whats_new.load(bad), {"releases": []})
            bad.write_text("[1]")
            self.assertEqual(whats_new.load(bad), {"releases": []})
            bad.write_text("{nope")
            self.assertEqual(whats_new.load(bad), {"releases": []})

    def test_since_lists_user_facing_and_names_internal_only(self):
        shown = whats_new.since(NOTES, "1.2.0")
        self.assertEqual([r["version"] for r in shown["listed"]], ["1.3.0"])
        self.assertEqual(shown["quiet"], ["1.2.1"])
        self.assertEqual(whats_new.since(NOTES, "garbage"), {"listed": [], "quiet": []})
        self.assertEqual(
            [r["version"] for r in whats_new.since(NOTES, None)["listed"]],
            ["1.3.0", "1.2.0"],
        )

    def test_panel_opens_only_after_a_user_facing_upgrade(self):
        self.assertIsNone(whats_new.panel(NOTES, "1.3.0", None, False))  # first visit
        self.assertIsNone(whats_new.panel(NOTES, "1.3.0", "1.3.0", False))
        self.assertIsNone(whats_new.panel(NOTES, "0.0.0-dev", "1.2.0", False))
        quiet_only = {"releases": [NOTES["releases"][1]]}
        self.assertIsNone(whats_new.panel(quiet_only, "1.2.1", "1.2.0", False))
        self.assertEqual(
            whats_new.panel(NOTES, "v1.3.0", "v1.2.0", False)["since"], "1.2.0"
        )
        self.assertIsNone(whats_new.panel(NOTES, "1.3.0", "1.2.0", True)["since"])


class DashboardPanelTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        path = Path(self.tmp.name) / "changelog.json"
        path.write_text(json.dumps(NOTES))
        server = StatusServer(
            "test-noip-bot", FakeStateStore, app_version="1.3.0", changelog_path=path
        )
        self.client = server.app.test_client()
        patcher = patch.dict(os.environ, {"STATUS_TOKEN": STATUS_TOKEN})
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_first_visit_records_version_without_panel(self):
        response = self.client.get("/", headers=AUTH)
        self.assertNotIn(b"whatsNewTitle", response.data)
        self.assertIn("noip_seen_version=1.3.0", response.headers["Set-Cookie"])
        self.assertIn("HttpOnly", response.headers["Set-Cookie"])

    def test_upgrade_shows_panel_until_dismissed(self):
        self.client.set_cookie(whats_new.SEEN_COOKIE, "1.2.0")
        page = self.client.get("/", headers=AUTH).data.decode()
        self.assertIn("What's new since v1.2.0", page)
        self.assertIn('class="breaking"', page)
        self.assertIn("&lt;b&gt;renew&lt;/b&gt; earlier", page)  # escaped
        self.assertIn("+ 2 internal changes", page)
        self.assertIn("Also v1.2.1: internal changes only.", page)
        self.assertNotIn("old fix", page)
        self.assertNotIn("<script", page)
        with self.client.session_transaction() as session:
            token = session["csrf_token"]
        self.assertEqual(
            self.client.post("/whats-new/seen", headers=AUTH, data={}).status_code, 400
        )
        done = self.client.post(
            "/whats-new/seen", headers=AUTH, data={"csrf_token": token}
        )
        self.assertEqual(done.status_code, 302)
        self.assertIn("noip_seen_version=1.3.0", done.headers["Set-Cookie"])
        self.assertNotIn(b"whatsNewTitle", self.client.get("/", headers=AUTH).data)

    def test_version_badge_reopens_latest_notes(self):
        self.client.set_cookie(whats_new.SEEN_COOKIE, "1.3.0")
        page = self.client.get("/?whats_new=1", headers=AUTH).data.decode()
        self.assertIn('id="whatsNewTitle">What\'s new<', page)
        self.assertIn("old fix", page)
        self.assertIn('href="/?whats_new=1"', page)

    def test_dismiss_requires_sign_in(self):
        response = self.client.post("/whats-new/seen")
        self.assertEqual(response.status_code, 302)
        self.assertIn("/login", response.headers["Location"])

    def test_build_without_notes_says_so_when_requested(self):
        server = StatusServer(
            "x",
            FakeStateStore,
            app_version="1.3.0",
            changelog_path=Path(self.tmp.name) / "missing.json",
        )
        page = server.app.test_client().get("/?whats_new=1", headers=AUTH).data
        self.assertIn(b"No release notes are included in this build.", page)


if __name__ == "__main__":
    unittest.main()
