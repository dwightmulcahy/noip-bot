import logging
import os
import time

import click
import click_config_file
from apscheduler.schedulers.background import BackgroundScheduler

from app_config import AppConfig
from application import NoIpApplication, RenewalUpdateError
from emailServer import MarkdownEmailServer, VerificationCodeReader
from logging_config import configure_logging
from utils import findFreePort, getMyIpAddr
from version import get_version


configure_logging()
log = logging.getLogger(__name__)

APP_NAME = os.path.splitext(os.path.basename(__file__))[0]
APP_DATE = time.strftime("%Y-%m-%d", time.localtime(os.path.getmtime(__file__)))
VERSION = get_version()
DEFAULT_TIMEZONE = os.environ.get("TZ", "America/Costa_Rica")
MAX_CHECK_INTERVAL_DAYS = max(1, int(os.environ.get("MAX_CHECK_INTERVAL_DAYS", "5")))


def configure_library_logging() -> None:
    for logger_name in ("werkzeug", "requests", "urllib3"):
        logging.getLogger(logger_name).setLevel(logging.ERROR)
    logging.getLogger("apscheduler").setLevel(logging.WARNING)


def build_email_services(
    gmail_id: str,
    gmail_token: str,
    verification_email: str,
    verification_token: str,
    debug: bool,
):
    gmail_server = None
    if gmail_token:
        log.info("Gmail server enabled.")
        gmail_server = MarkdownEmailServer(APP_NAME, gmail_id, gmail_token, debug=debug)
    else:
        log.warning("Gmail server token not defined.")

    if verification_token:
        code_reader = VerificationCodeReader(verification_email, verification_token)
    elif gmail_token:
        log.warning(
            "NOIP_VERIFICATION_EMAIL_TOKEN not set; falling back to "
            "GMAIL_ID/GMAIL_TOKEN for verification-code lookup."
        )
        code_reader = VerificationCodeReader(gmail_id, gmail_token)
    else:
        code_reader = None
    return gmail_server, code_reader


@click.command()
@click.version_option(
    version=VERSION, message=f'{APP_NAME} version "{VERSION}" {APP_DATE}'
)
@click.option("--verbose", "-v", is_flag=True, default=False)
@click.option("--test", "-t", is_flag=True, default=False)
@click.option("--dry-run", envvar="DRY_RUN", is_flag=True, default=False)
@click.option(
    "--skip-initial-run", envvar="SKIP_INITIAL_RUN", is_flag=True, default=False
)
@click.option("--debug", "-d", envvar="DEBUG", is_flag=True, default=False)
@click.option("--gmail-id", "--gmail_id", "-gid", envvar="GMAIL_ID", default="")
@click.option("--gmail-token", "--gmail_token", "-gt", envvar="GMAIL_TOKEN", default="")
@click.option(
    "--noip-verification-email",
    "--noip_verification_email",
    "-nve",
    envvar="NOIP_VERIFICATION_EMAIL",
    default="",
)
@click.option(
    "--noip-verification-email-token",
    "--noip_verification_email_token",
    "-nvet",
    envvar="NOIP_VERIFICATION_EMAIL_TOKEN",
    default="",
)
@click.option(
    "--bind-address", "--bind_addr", "-ba", envvar="BIND_ADDR", default=getMyIpAddr()
)
@click.option("--port", "-p", envvar="PORT", default=findFreePort(), type=int)
@click.option("--noip-id", "--noip_id", "-nid", envvar="NOIP_ID", default="")
@click.option(
    "--noip-password", "--noip_pw", "-npw", envvar="NOIP_PASSWORD", default=""
)
@click_config_file.configuration_option(
    config_file_name=os.path.dirname(os.path.realpath(__file__)) + "/config"
)
def main(
    verbose: bool,
    test: bool,
    dry_run: bool,
    skip_initial_run: bool,
    debug: bool,
    gmail_id: str,
    gmail_token: str,
    noip_verification_email: str,
    noip_verification_email_token: str,
    bind_address: str,
    port: int,
    noip_id: str,
    noip_password: str,
) -> None:
    log.info("Started %s", APP_NAME)
    configure_library_logging()
    gmail_server, code_reader = build_email_services(
        gmail_id,
        gmail_token,
        noip_verification_email,
        noip_verification_email_token,
        debug,
    )
    scheduler = BackgroundScheduler(
        job_defaults={"misfire_grace_time": 60}, timezone=DEFAULT_TIMEZONE
    )
    config = AppConfig(
        noip_id=noip_id,
        noip_password=noip_password,
        bind_address=bind_address,
        port=port,
        timezone=DEFAULT_TIMEZONE,
        max_check_interval_days=MAX_CHECK_INTERVAL_DAYS,
        scheduler=scheduler,
        gmail_server=gmail_server,
        code_reader=code_reader,
        debug=debug,
        dry_run=bool(dry_run or test),
        skip_initial_run=skip_initial_run,
        verbose=verbose,
        test=test,
    )
    scheduler.start()
    application = NoIpApplication(config, APP_NAME)

    try:
        application.run()
    except (KeyboardInterrupt, SystemExit):
        log.warning("Keyboard interrupt intercepted.")
        application.send_email(
            config.noip_id,
            "NOIP-BOT stopped",
            "NOIP-BOT stopped via Keyboard interrupt",
        )
    except RuntimeError as error:
        log.exception("NOIP-BOT runtime exception")
        if not isinstance(error, RenewalUpdateError):
            application.send_email(config.noip_id, "NOIP-BOT Runtime exception", error)
        raise
    except Exception as error:
        log.exception("NOIP-BOT unknown exception")
        application.send_email(config.noip_id, "NOIP-BOT unknown exception", error)
        raise
    finally:
        log.info("Shutting down scheduler task.")
        scheduler.shutdown()
        log.info("Shutting down `%s`.", APP_NAME)


if __name__ == "__main__":
    main()
