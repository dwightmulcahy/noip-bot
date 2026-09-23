from dataclasses import dataclass
from typing import Any, Protocol
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


class Scheduler(Protocol):
    def add_job(self, function: Any, trigger: str, **kwargs: Any) -> Any: ...

    def shutdown(self) -> None: ...


@dataclass(frozen=True, slots=True)
class AppConfig:
    noip_id: str
    noip_password: str
    bind_address: str
    port: int
    timezone: str
    max_check_interval_days: int
    scheduler: Scheduler
    gmail_server: Any = None
    code_reader: Any = None
    debug: bool = False
    dry_run: bool = False
    skip_initial_run: bool = False
    verbose: bool = False
    test: bool = False

    def __post_init__(self) -> None:
        if not 1 <= self.port <= 65535:
            raise ValueError("port must be between 1 and 65535")
        if self.max_check_interval_days < 1:
            raise ValueError("max_check_interval_days must be at least 1")
        if not self.skip_initial_run and (not self.noip_id or not self.noip_password):
            raise ValueError(
                "NOIP_ID and NOIP_PASSWORD are required unless SKIP_INITIAL_RUN is enabled"
            )
        try:
            ZoneInfo(self.timezone)
        except ZoneInfoNotFoundError as exc:
            raise ValueError(f"unknown timezone: {self.timezone}") from exc
