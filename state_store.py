import json
import os
import tempfile
import threading
from contextlib import contextmanager
from copy import deepcopy
from datetime import datetime, timezone
from typing import Any

import fcntl


def utc_now():
    return datetime.now(timezone.utc).isoformat()


class StateStore:
    _PROCESS_LOCK = threading.RLock()
    DEFAULT_STATE: dict[str, Any] = {
        "schema_version": 4,
        "last_run": None,
        "last_success": None,
        "last_error": None,
        "next_check": None,
        "dry_run": False,
        "would_renew": [],
        "notifications": {
            "enabled": False,
            "last_attempt": None,
            "last_success": None,
            "last_error": None,
        },
        "retry": {
            "consecutive_failures": 0,
            "next_retry": None,
        },
        "hosts": {},
    }

    def __init__(self, path=None):
        default_path = os.path.join(os.getcwd(), "data", "state.json")
        self.path = path or os.environ.get("STATE_FILE", default_path)
        self.state = self._load()

    @contextmanager
    def _exclusive_lock(self):
        directory = os.path.dirname(os.path.abspath(self.path))
        os.makedirs(directory, exist_ok=True)
        with self._PROCESS_LOCK:
            with open(f"{self.path}.lock", "a+", encoding="utf-8") as lock_file:
                fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
                try:
                    yield
                finally:
                    fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)

    def _load(self):
        try:
            with open(self.path, "r", encoding="utf-8") as state_file:
                loaded = json.load(state_file)
        except FileNotFoundError:
            return deepcopy(self.DEFAULT_STATE)
        except (OSError, ValueError) as exc:
            raise RuntimeError(
                f"Unable to load renewal state {self.path}: {exc}"
            ) from exc
        state = deepcopy(self.DEFAULT_STATE)
        state.update(loaded)
        state["schema_version"] = self.DEFAULT_STATE["schema_version"]
        state["hosts"] = loaded.get("hosts", {})
        notifications: dict[str, Any] = deepcopy(self.DEFAULT_STATE["notifications"])
        notifications.update(loaded.get("notifications", {}))
        state["notifications"] = notifications
        retry: dict[str, Any] = deepcopy(self.DEFAULT_STATE["retry"])
        retry.update(loaded.get("retry", {}))
        state["retry"] = retry
        return state

    def _save_unlocked(self):
        directory = os.path.dirname(os.path.abspath(self.path))
        os.makedirs(directory, exist_ok=True)
        descriptor, temporary_path = tempfile.mkstemp(
            prefix=".state-", suffix=".json", dir=directory
        )
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8") as state_file:
                json.dump(self.state, state_file, indent=2, sort_keys=True)
                state_file.write("\n")
                state_file.flush()
                os.fsync(state_file.fileno())
            os.replace(temporary_path, self.path)
        except Exception:
            try:
                os.unlink(temporary_path)
            except FileNotFoundError:
                pass
            raise

    def save(self):
        with self._exclusive_lock():
            self._save_unlocked()

    def _update(self, mutation):
        with self._exclusive_lock():
            self.state = self._load()
            mutation(self.state)
            self._save_unlocked()

    def record_run_started(self, dry_run=False):
        def mutation(state):
            state["last_run"] = utc_now()
            state["last_error"] = None
            state["dry_run"] = bool(dry_run)
            state["would_renew"] = []

        self._update(mutation)

    def record_would_renew(self, hostnames):
        self._update(lambda state: state.update(would_renew=list(hostnames)))

    def record_host(
        self, hostname, old_data_update, new_data_update, observed_details=None
    ):
        def mutation(state):
            host = state["hosts"].setdefault(hostname, {})
            if observed_details:
                host.update(observed_details)
            host.update(
                {
                    "last_verified_renewal": utc_now(),
                    "previous_data_update": old_data_update,
                    "data_update": new_data_update,
                }
            )

        self._update(mutation)

    def record_inventory(self, inventory):
        def mutation(state):
            observed = utc_now()
            for hostname, host in state["hosts"].items():
                if hostname not in inventory:
                    host["active"] = False
            for hostname, details in inventory.items():
                host = state["hosts"].setdefault(hostname, {})
                host.update(details)
                host["last_observed"] = observed
                host["active"] = True

        self._update(mutation)

    def record_success(
        self, next_check=None, host_expirations=None, next_renewal_days=None
    ):
        def mutation(state):
            state["last_success"] = utc_now()
            state["last_error"] = None
            state["next_check"] = next_check
            state["next_renewal_days"] = next_renewal_days
            state["retry"] = deepcopy(self.DEFAULT_STATE["retry"])
            for hostname, expires_in_days in (host_expirations or {}).items():
                host = state["hosts"].setdefault(hostname, {})
                host["expires_in_days"] = expires_in_days
                host["last_observed"] = utc_now()

        self._update(mutation)

    def record_next_check(self, next_check):
        self._update(lambda state: state.update(next_check=next_check))

    def record_retry_failure(self, error):
        result = {}

        def mutation(state):
            failure_count = int(state["retry"].get("consecutive_failures", 0)) + 1
            state["last_error"] = {
                "timestamp": utc_now(),
                "message": str(error),
                "type": type(error).__name__,
            }
            state["retry"]["consecutive_failures"] = failure_count
            state["retry"]["next_retry"] = None
            result["failure_count"] = failure_count

        self._update(mutation)
        return result["failure_count"]

    def record_retry_scheduled(self, next_retry):
        def mutation(state):
            state["next_check"] = next_retry
            state["retry"]["next_retry"] = next_retry

        self._update(mutation)

    def record_failure(self, error):
        def mutation(state):
            state["last_error"] = {
                "timestamp": utc_now(),
                "message": str(error),
                "type": type(error).__name__,
            }

        self._update(mutation)

    def set_notifications_enabled(self, enabled):
        self._update(lambda state: state["notifications"].update(enabled=bool(enabled)))

    def record_notification_success(self):
        def mutation(state):
            timestamp = utc_now()
            state["notifications"].update(
                {
                    "enabled": True,
                    "last_attempt": timestamp,
                    "last_success": timestamp,
                    "last_error": None,
                }
            )

        self._update(mutation)

    def record_notification_failure(self, error):
        def mutation(state):
            timestamp = utc_now()
            state["notifications"].update(
                {
                    "enabled": True,
                    "last_attempt": timestamp,
                    "last_error": {
                        "timestamp": timestamp,
                        "message": str(error),
                        "type": type(error).__name__,
                    },
                }
            )

        self._update(mutation)
