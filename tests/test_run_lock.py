import json
import os
import tempfile
import unittest

from run_lock import WholeRunLock


class WholeRunLockTests(unittest.TestCase):
    def test_second_owner_is_rejected_and_reports_metadata(self):
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, "renewal.run.lock")
            first = WholeRunLock(path)
            second = WholeRunLock(path)

            self.assertTrue(first.acquire())
            self.assertFalse(second.acquire())
            self.assertEqual(second.owner["pid"], os.getpid())
            self.assertIn("hostname", second.owner)
            self.assertIn("acquired_at", second.owner)
            first.release()

    def test_lock_is_reacquirable_after_release(self):
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, "renewal.run.lock")
            first = WholeRunLock(path)
            self.assertTrue(first.acquire())
            first.release()

            second = WholeRunLock(path)
            self.assertTrue(second.acquire())
            second.release()

    def test_lock_metadata_is_valid_json(self):
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, "renewal.run.lock")
            lock = WholeRunLock(path)
            self.assertTrue(lock.acquire())
            with open(path, encoding="utf-8") as lock_file:
                metadata = json.load(lock_file)
            lock.release()

            self.assertEqual(metadata["pid"], os.getpid())

    def test_context_manager_releases_after_exception(self):
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, "renewal.run.lock")
            with self.assertRaisesRegex(RuntimeError, "failed"):
                with WholeRunLock(path) as lock:
                    self.assertIsNotNone(lock._file)
                    raise RuntimeError("failed")

            replacement = WholeRunLock(path)
            self.assertTrue(replacement.acquire())
            replacement.release()


if __name__ == "__main__":
    unittest.main()
