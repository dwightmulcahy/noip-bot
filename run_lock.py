import fcntl
import json
import os
import socket
from datetime import datetime, timezone
from pathlib import Path
from typing import TextIO


class WholeRunLock:
    """Non-blocking inter-process lock covering an entire renewal run."""

    def __init__(self, path: str) -> None:
        self.path = path
        self.owner: dict[str, object] = {}
        self._file: TextIO | None = None

    @classmethod
    def for_state_file(cls, state_file: str) -> "WholeRunLock":
        path = os.environ.get("RUN_LOCK_FILE", f"{state_file}.run.lock")
        return cls(path)

    def acquire(self) -> bool:
        Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        lock_file = open(self.path, "a+", encoding="utf-8")
        try:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            lock_file.seek(0)
            try:
                self.owner = json.load(lock_file)
            except (OSError, ValueError):
                self.owner = {}
            lock_file.close()
            return False

        self.owner = {
            "pid": os.getpid(),
            "hostname": socket.gethostname(),
            "acquired_at": datetime.now(timezone.utc).isoformat(),
        }
        lock_file.seek(0)
        lock_file.truncate()
        json.dump(self.owner, lock_file, sort_keys=True)
        lock_file.write("\n")
        lock_file.flush()
        os.fsync(lock_file.fileno())
        self._file = lock_file
        return True

    def release(self) -> None:
        if self._file is None:
            return
        fcntl.flock(self._file.fileno(), fcntl.LOCK_UN)
        self._file.close()
        self._file = None

    def __enter__(self) -> "WholeRunLock":
        self.acquire()
        return self

    def __exit__(self, exception_type, exception, traceback) -> None:
        self.release()
