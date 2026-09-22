import json
import os
import tempfile
import threading
from copy import deepcopy
from datetime import datetime, timezone


def utc_now():
    return datetime.now(timezone.utc).isoformat()


class StateStore:
    DEFAULT_STATE = {
        "schema_version": 3,
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
        "hosts": {},
    }

    def __init__(self, path=None):
        default_path = os.path.join(os.getcwd(), "data", "state.json")
        self.path = path or os.environ.get("STATE_FILE", default_path)
        self._lock = threading.Lock()
        self.state = self._load()

    def _load(self):
        try:
            with open(self.path, "r", encoding="utf-8") as state_file:
                loaded = json.load(state_file)
        except FileNotFoundError:
            return deepcopy(self.DEFAULT_STATE)
        except (OSError, ValueError) as exc:
            raise RuntimeError(f"Unable to load renewal state {self.path}: {exc}") from exc
        state = deepcopy(self.DEFAULT_STATE)
        state.update(loaded)
        state["schema_version"] = self.DEFAULT_STATE["schema_version"]
        state["hosts"] = loaded.get("hosts", {})
        notifications = deepcopy(self.DEFAULT_STATE["notifications"])
        notifications.update(loaded.get("notifications", {}))
        state["notifications"] = notifications
        return state

    def save(self):
        directory = os.path.dirname(os.path.abspath(self.path))
        os.makedirs(directory, exist_ok=True)
        with self._lock:
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

    def record_run_started(self, dry_run=False):
        self.state["last_run"] = utc_now()
        self.state["last_error"] = None
        self.state["dry_run"] = bool(dry_run)
        self.state["would_renew"] = []
        self.save()

    def record_would_renew(self, hostnames):
        self.state["would_renew"] = list(hostnames)
        self.save()

    def record_host(self, hostname, old_data_update, new_data_update, observed_details=None):
        host = self.state["hosts"].setdefault(hostname, {})
        if observed_details:
            host.update(observed_details)
        host.update({
            "last_verified_renewal": utc_now(),
            "previous_data_update": old_data_update,
            "data_update": new_data_update,
        })
        self.save()

    def record_inventory(self, inventory):
        observed = utc_now()
        for hostname, host in self.state["hosts"].items():
            if hostname not in inventory:
                host["active"] = False
        for hostname, details in inventory.items():
            host = self.state["hosts"].setdefault(hostname, {})
            host.update(details)
            host["last_observed"] = observed
            host["active"] = True
        self.save()

    def record_success(self, next_check=None, host_expirations=None, next_renewal_days=None):
        self.state["last_success"] = utc_now()
        self.state["last_error"] = None
        self.state["next_check"] = next_check
        self.state["next_renewal_days"] = next_renewal_days
        for hostname, expires_in_days in (host_expirations or {}).items():
            host = self.state["hosts"].setdefault(hostname, {})
            host["expires_in_days"] = expires_in_days
            host["last_observed"] = utc_now()
        self.save()

    def record_next_check(self, next_check):
        self.state["next_check"] = next_check
        self.save()

    def record_failure(self, error):
        self.state["last_error"] = {
            "timestamp": utc_now(),
            "message": str(error),
            "type": type(error).__name__,
        }
        self.save()

    def set_notifications_enabled(self, enabled):
        self.state["notifications"]["enabled"] = bool(enabled)
        self.save()

    def record_notification_success(self):
        timestamp = utc_now()
        notifications = self.state["notifications"]
        notifications.update({
            "enabled": True,
            "last_attempt": timestamp,
            "last_success": timestamp,
            "last_error": None,
        })
        self.save()

    def record_notification_failure(self, error):
        timestamp = utc_now()
        notifications = self.state["notifications"]
        notifications.update({
            "enabled": True,
            "last_attempt": timestamp,
            "last_error": {
                "timestamp": timestamp,
                "message": str(error),
                "type": type(error).__name__,
            },
        })
        self.save()
