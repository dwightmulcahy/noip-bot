import calendar
import datetime
import logging
from datetime import date, timedelta
from random import randrange, uniform
from typing import Any, Callable
from zoneinfo import ZoneInfo

from dateutil.relativedelta import relativedelta

from app_config import AppConfig
from githubMarkdown import GithubMarkdown
from noip_renew import Robot
from notifications import send_notification
from run_lock import WholeRunLock
from scheduling import (
    cap_future_check,
    days_until_check,
    future_check,
    retry_delay_seconds,
    should_notify_failure,
)
from state_store import StateStore
from status_server import setPageMsg, startWebServer
from utils import getMyIpAddr


log = logging.getLogger(__name__)


class RenewalUpdateError(RuntimeError):
    """A renewal failure already handled by retry and notification logic."""


class RenewalRunLockedError(RenewalUpdateError):
    """Raised when another process already owns the renewal-run lock."""


class NoIpApplication:
    def __init__(
        self,
        config: AppConfig,
        app_name: str = "noip_bot",
        robot_factory: Callable[..., Any] = Robot,
    ) -> None:
        self.config = config
        self.app_name = app_name
        self.robot_factory = robot_factory

    def send_email(self, send_to: str, subject: str, body: object) -> bool:
        try:
            notification_state = StateStore()
        except Exception:
            notification_state = None
            log.exception(
                "Unable to load notification state; attempting delivery without persistence",
                extra={"event": "notification_state_unavailable"},
            )
        return send_notification(
            server=self.config.gmail_server,
            send_to=send_to,
            subject=subject,
            body=body,
            state_store=notification_state,
            logger=log,
        )

    def update_hosts(self) -> None:
        state_store = StateStore()
        run_lock = WholeRunLock.for_state_file(state_store.path)
        if not run_lock.acquire():
            log.warning(
                "Renewal run skipped because another process owns the lock",
                extra={
                    "event": "run_skipped_locked",
                    "lock_file": run_lock.path,
                    "lock_owner": run_lock.owner,
                },
            )
            raise RenewalRunLockedError("another renewal run is already in progress")
        try:
            self._update_hosts_locked(state_store)
        finally:
            run_lock.release()

    def _update_hosts_locked(self, state_store: StateStore) -> None:
        log.info(
            "Updating Hosts.",
            extra={"event": "run_lock_acquired"},
        )
        previous_failures = int(
            state_store.state.get("retry", {}).get("consecutive_failures", 0)
        )
        try:
            noip = self.robot_factory(
                self.config.noip_id,
                self.config.noip_password,
                2 if self.config.debug else 0,
                code_reader=self.config.code_reader,
                state_store=state_store,
                dry_run=self.config.dry_run,
            )
            noip.run()
        except Exception as error:
            failure_count = state_store.record_retry_failure(error)
            retry_delay = retry_delay_seconds(failure_count, uniform(-0.1, 0.1))
            retry_date = datetime.datetime.now(
                ZoneInfo(self.config.timezone)
            ) + timedelta(seconds=retry_delay)
            self.config.scheduler.add_job(
                self.update_hosts,
                "date",
                run_date=retry_date,
                id="Update Hosts",
                replace_existing=True,
            )
            state_store.record_retry_scheduled(retry_date.isoformat())
            log.exception(
                "No-IP update failed; retry %s scheduled for %s",
                failure_count,
                retry_date.isoformat(),
                extra={
                    "event": "retry_scheduled",
                    "consecutive_failures": failure_count,
                    "retry_delay_seconds": retry_delay,
                    "next_retry": retry_date.isoformat(),
                },
            )
            if should_notify_failure(failure_count):
                self.send_email(
                    self.config.noip_id,
                    "NOIP-Bot renewal failure",
                    "\n".join(
                        [
                            f"Renewal check failed ({type(error).__name__}).",
                            f"Consecutive failures: {failure_count}.",
                            f"Next retry: {retry_date.isoformat()}.",
                            f"Error: {error}",
                        ]
                    ),
                )
            raise RenewalUpdateError(str(error)) from error

        for host_name in noip.updatedHosts:
            log.info('Updated host "%s" for 30 more days', host_name)

        check_delay = days_until_check(
            noip.next_renewal,
            1 + randrange(5),
            self.config.max_check_interval_days,
        )
        next_check_date = date.today() + timedelta(days=check_delay)
        next_check_hour = 9 + randrange(8)
        next_check_minute = randrange(59)
        log.info(
            "Next hosts update scheduled on %s %s at %02d:%02d.",
            calendar.month_abbr[next_check_date.month],
            next_check_date.day,
            next_check_hour,
            next_check_minute,
            extra={
                "event": "next_check_scheduled",
                "check_delay_days": check_delay,
                "max_check_interval_days": self.config.max_check_interval_days,
            },
        )
        next_check = datetime.datetime(
            year=next_check_date.year,
            month=next_check_date.month,
            day=next_check_date.day,
            hour=next_check_hour,
            minute=next_check_minute,
            second=0,
            tzinfo=ZoneInfo(self.config.timezone),
        )
        self.config.scheduler.add_job(
            self.update_hosts,
            "date",
            run_date=next_check,
            id="Update Hosts",
            replace_existing=True,
        )
        state_store.record_next_check(next_check.isoformat())

        if previous_failures:
            self.send_email(
                self.config.noip_id,
                "NOIP-Bot renewal recovered",
                f"Renewal checks recovered after {previous_failures} consecutive failures.",
            )

        email_body = self._build_update_summary(
            noip, next_check_date, next_check_hour, next_check_minute
        )
        setPageMsg(email_body)
        if noip.updatedHosts:
            self.send_email(
                self.config.noip_id,
                "NOIP-Bot updated domains",
                email_body,
            )

    @staticmethod
    def _build_update_summary(
        noip: Any,
        next_check_date: date,
        next_check_hour: int,
        next_check_minute: int,
    ) -> str:
        markdown = GithubMarkdown()
        if noip.dry_run and noip.wouldUpdateHosts:
            update_summary = (
                "Dry run: the following hostnames would have been updated: "
                + ", ".join(noip.wouldUpdateHosts)
                + "."
            )
        elif noip.updatedHosts:
            update_summary = (
                "The following hostnames have been updated: "
                + ", ".join(noip.updatedHosts)
                + "."
            )
        else:
            update_summary = markdown.bolditalics(
                "No hostnames were updated during this update."
            )
        updated_hosts = markdown.linebreak(markdown.linebreak(update_summary))
        host_table = "".join(
            [
                "<style> table, th, td { border: 2px solid black; } </style>\n",
                f"| {markdown.bold('Host Name')} | {markdown.bold('Expires')} |\n",
                markdown.linebreak("|:-------|:-----:|"),
            ]
        )
        for host_name, expiration_day in noip.host_expirations.items():
            expiration_date = (
                date.today() + relativedelta(days=+expiration_day)
            ).strftime("%m-%d-%Y")
            host_table += markdown.linebreak(f"| {host_name} | {expiration_date} |")
        return "".join(
            [
                markdown.linebreak(f"{updated_hosts}{host_table}"),
                "Next update scheduled for "
                f"{markdown.bold(next_check_date.strftime('%m/%d/%Y'))} at ",
                markdown.bold(f"{next_check_hour:02d}:{next_check_minute:02d}."),
            ]
        )

    def run(self) -> None:
        self.send_email(
            self.config.noip_id,
            "NOIP-Bot started",
            GithubMarkdown().header(
                "NOIP-Bot started. Any updates and errors will be sent via email.",
                level=3,
            ),
        )
        state_store = StateStore()
        now = datetime.datetime.now(ZoneInfo(self.config.timezone))
        restored_check = future_check(state_store.state.get("next_check"), now)
        capped_check = cap_future_check(
            restored_check, now, self.config.max_check_interval_days
        )
        if capped_check and capped_check != restored_check:
            restored_check = capped_check
            state_store.record_next_check(restored_check.isoformat())
            log.warning(
                "Persisted schedule exceeded safety cap and was shortened",
                extra={
                    "event": "restored_schedule_capped",
                    "next_check": restored_check.isoformat(),
                    "max_check_interval_days": self.config.max_check_interval_days,
                },
            )
        if self.config.skip_initial_run:
            log.info(
                "Initial renewal skipped by configuration",
                extra={"event": "initial_renewal_skipped"},
            )
        elif restored_check and not self.config.dry_run:
            self.config.scheduler.add_job(
                self.update_hosts,
                "date",
                run_date=restored_check,
                id="Update Hosts",
                replace_existing=True,
            )
            log.info(
                "Restored next hosts update from persistent state",
                extra={
                    "event": "schedule_restored",
                    "next_check": restored_check.isoformat(),
                },
            )
        else:
            if self.config.dry_run:
                log.info(
                    "Dry run bypassing restored schedule",
                    extra={"event": "dry_run_schedule_bypass", "dry_run": True},
                )
            self.update_hosts()

        log.info(
            "Bind Address: %s acceptable %s:%s",
            self.config.bind_address,
            getMyIpAddr(),
            self.config.port,
        )
        startWebServer(
            self.app_name,
            bind=self.config.bind_address,
            port=self.config.port,
        )
