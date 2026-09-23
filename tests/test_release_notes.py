import unittest
from unittest.mock import patch

from scripts.generate_release_notes import render


class ReleaseNotesTests(unittest.TestCase):
    @patch("scripts.generate_release_notes.previous_tag", return_value="v0.4.0")
    @patch(
        "scripts.generate_release_notes.commit_subjects",
        return_value=[
            ("abc1234", "feat(status): add email login"),
            ("def5678", "fix: prevent release race"),
            ("987abcd", "docs: explain Docker tags"),
        ],
    )
    def test_groups_conventional_commits(self, _subjects, _previous):
        notes = render("v0.5.0", "dwightmulcahy/noip-bot")

        self.assertIn("# No-IP Bot 0.5.0", notes)
        self.assertIn("## ✨ Features", notes)
        self.assertIn("**status:** add email login (abc1234)", notes)
        self.assertIn("## 🐛 Bug fixes", notes)
        self.assertIn("docker pull dwightmulcahy/noip-bot:0.5.0", notes)
        self.assertIn("compare/v0.4.0...v0.5.0", notes)

    @patch("scripts.generate_release_notes.previous_tag", return_value=None)
    @patch(
        "scripts.generate_release_notes.commit_subjects",
        return_value=[("abc1234", "feat!: replace legacy configuration")],
    )
    def test_highlights_breaking_changes(self, _subjects, _previous):
        notes = render("0.1.0", "dwightmulcahy/noip-bot")

        self.assertIn("## 💥 Breaking changes", notes)
        self.assertIn("replace legacy configuration", notes)


if __name__ == "__main__":
    unittest.main()
