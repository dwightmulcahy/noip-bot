import os
import time
import calendar
import sys
import datetime
from datetime import timedelta, date
from random import randrange
from dateutil.relativedelta import relativedelta

from zoneinfo import ZoneInfo

from noip_renew import Robot
import click as click
from apscheduler.schedulers.background import BackgroundScheduler  # https://github.com/agronholm/apscheduler
from emailServer import MarkdownEmailServer, VerificationCodeReader
from flask_template import startWebServer, setPageMsg
from githubMarkdown import GithubMarkdown
from settings import Settings
from utils import findFreePort, getMyIpAddr
import click_config_file   # https://github.com/phha/click_config_file
from logging_config import configure_logging
from state_store import StateStore

# formatting for log messages
import logging
configure_logging()
log = logging.getLogger(__name__)

LOCAL_TIMEZONE = os.environ.get("TZ", "America/Costa_Rica")
# LOCAL_TIMEZONE = get_localzone().zone

# Application info
# APP_NAME = 'NOIP-BOT'
APP_NAME = os.path.splitext(os.path.basename(__file__))[0]
APP_DATE = time.strftime('%Y-%m-%d', time.localtime(os.path.getmtime(__file__)))
VERSION = '0.1.3'

# setting storage
settings = Settings()

# active hosts for webpage to display
emailBody = ''

def sendEmail(sendTo, subject, body):
    if not settings.gmailServer:
        log.error(f'Cannot send email (subject: `{subject}`) — Gmail server is not configured '
                  f'(GMAIL_TOKEN missing or not picked up from config/env).')
        return
    wasSent = settings.gmailServer.sendEmail(sendTo, subject, str(body))
    if wasSent:
        log.info(f'Email was sent to {sendTo} with title `{subject}`')
    else:
        log.error(f'Email was not sent to {sendTo} with title `{subject}`')


def updateHosts():
    log.info('Updating Hosts.')
    state_store = StateStore()
    try:
        noip = Robot(
            settings.noip_id,
            settings.noip_pw,
            2 if settings.debug else 0,
            code_reader=settings.codeReader,
            state_store=state_store,
        )
        noip.run()
    except Exception:
        retry_date = datetime.datetime.now(ZoneInfo(LOCAL_TIMEZONE)) + timedelta(days=1)
        settings.scheduler.add_job(
            updateHosts, "date", run_date=retry_date, id='Update Hosts', replace_existing=True
        )
        state_store.record_next_check(retry_date.isoformat())
        log.exception('No-IP update failed; retry scheduled for %s', retry_date.isoformat())
        raise

    # show the hosts that got updated
    for hostName in noip.updatedHosts:
        log.info(f'Updated host "{hostName}" for 30 more days')

    # get the next update and schedule it for random time 7 days before the required update
    nextCheckDate, nextCheckHour, nextCheckMin = \
        date.today() + timedelta(days=(1+randrange(5) if noip.next_renewal == 0 else noip.next_renewal - 6)), 9+randrange(8), randrange(59)
    log.info(f'Next hosts update scheduled on {calendar.month_abbr[nextCheckDate.month]} {nextCheckDate.day} at {nextCheckHour:02d}:{nextCheckMin:02d}.')
    next_check = datetime.datetime(
        year=nextCheckDate.year,
        month=nextCheckDate.month,
        day=nextCheckDate.day,
        hour=nextCheckHour,
        minute=nextCheckMin,
        second=0,
        tzinfo=ZoneInfo(LOCAL_TIMEZONE),
    )
    settings.scheduler.add_job(
        updateHosts,
        "date", run_date=next_check,
        id='Update Hosts', replace_existing=True
    )
    state_store.record_next_check(next_check.isoformat())

    # Create Email with info on current domains and which were updated
    gmd = GithubMarkdown()

    # inform which Domains got updated to the user
    updatedHosts = gmd.linebreak(gmd.linebreak(
        'The following hostnames have been updated: ' + ', '.join(noip.updatedHosts) + '.'
        if noip.updatedHosts else gmd.bolditalics('No hostnames were updated during this update.')
    ))

    # Create a table of the active hosts and when the need to be updated again
    hostTable = ''.join([
        '<style> table, th, td { border: 2px solid black; } </style>\n',
        f'| {gmd.bold("Host Name")} | {gmd.bold("Expires")} |\n',
        gmd.linebreak('|:-------|:-----:|'),
    ])
    if noip.host_expirations:
        for host_name, expiration_day in noip.host_expirations.items():
            expirationDate = (date.today() + relativedelta(days=+expiration_day)).strftime("%m-%d-%Y")
            hostTable = ''.join([hostTable, gmd.linebreak(f'| {host_name} | {expirationDate} |')])

    emailBody = ''.join([
        gmd.linebreak(f'{updatedHosts}{hostTable}'),
        f'Next update scheduled for {gmd.bold(nextCheckDate.strftime("%m/%d/%Y"))} at ',
        gmd.bold(f'{nextCheckHour:02d}:{nextCheckMin:02d}.'),
    ])

    # send out email (only when something actually changed — no point
    # emailing "no hostnames were updated" every run)
    setPageMsg(emailBody)
    if noip.updatedHosts:
        sendEmail(
            sendTo=settings.noip_id,
            subject="NOIP-Bot updated domains",
            body=emailBody,
        )


def mainApp(bind, port):
    log.debug(f'mainApp() entered')

    sendEmail(
        sendTo=settings.noip_id,
        subject='NOIP-Bot started',
        body=GithubMarkdown().header('NOIP-Bot started. Any updates and errors will be sent via email.', level=3),
    )

    # start the initial scheduled threads for all domains
    updateHosts()

    # bind locally to a free port
    log.info(f'Bind Address: {bind} acceptable {getMyIpAddr()}:{port}')
    startWebServer(APP_NAME, bind=bind, port=port)


@click.command()
@click.version_option(version=VERSION, message=f'{APP_NAME} version \"{VERSION}\" {APP_DATE}')
@click.option('--verbose', '-v', is_flag=True, default=False)
@click.option('--test', '-t', is_flag=True, default=False)
@click.option('--debug', '-d', envvar='DEBUG', is_flag=True, default=False)
@click.option('--gmail_id', '-gid', envvar='GMAIL_ID', default='')
@click.option('--gmail_token', '-gt', envvar='GMAIL_TOKEN', default='')
@click.option('--noip_verification_email', '-nve', envvar='NOIP_VERIFICATION_EMAIL', default='')
@click.option('--noip_verification_email_token', '-nvet', envvar='NOIP_VERIFICATION_EMAIL_TOKEN', default='')
@click.option('--bind_addr', '-ba', envvar='BIND_ADDR', default=getMyIpAddr())
@click.option('--port', '-p', envvar='PORT', default=findFreePort())
@click.option('--noip_id', '-nid', envvar='NOIP_ID', default='')
@click.option('--noip_pw', '-npw', envvar='NOIP_PASSWORD', default='')
@click_config_file.configuration_option(config_file_name=os.path.dirname(os.path.realpath(__file__))+'/config')
def main(verbose, test, debug,
         gmail_id, gmail_token,
         noip_verification_email, noip_verification_email_token,
         bind_addr, port,
         noip_id, noip_pw
         ):
    global settings
    log.info(f'Started {APP_NAME}')

    # more verbose log when this is set and use flask webserver
    settings.debug = debug
    log.info(f'Debug set to {debug}')

    # quiet the output from some of the libs
    logging.getLogger('werkzeug').setLevel(logging.ERROR)
    logging.getLogger('requests').setLevel(logging.ERROR)
    logging.getLogger('urllib3').setLevel(logging.ERROR)
    logging.getLogger('apscheduler').setLevel(logging.WARNING)

    # get environment variable for gmail server
    if gmail_token:
        log.info(f'Gmail server enabled.')
        settings.gmailServer = MarkdownEmailServer(APP_NAME, gmail_id, gmail_token, debug=debug)
    else:
        log.warning('Gmail server token not defined.')

    # The account that RECEIVES noip.com's 2FA code is the noip.com account
    # holder's own inbox, which may differ from the bot's sending account.
    if noip_verification_email_token:
        settings.codeReader = VerificationCodeReader(noip_verification_email, noip_verification_email_token)
    elif gmail_token:
        log.warning('NOIP_VERIFICATION_EMAIL_TOKEN not set; falling back to GMAIL_ID/GMAIL_TOKEN for '
                     'verification-code lookup. Set NOIP_VERIFICATION_EMAIL(_TOKEN) if that account '
                     'is not the noip.com account holder\'s inbox.')
        settings.codeReader = VerificationCodeReader(gmail_id, gmail_token)
    else:
        settings.codeReader = None

    # start the scheduler out... nothing to do right now
    log.info('Starting scheduler.')
    settings.scheduler = BackgroundScheduler(job_defaults={'misfire_grace_time': 60}, timezone=LOCAL_TIMEZONE)
    settings.scheduler.start()

    # other settings
    settings.test = test
    settings.verbose = verbose

    # save off the noip logon info
    settings.noip_id = noip_id
    settings.noip_pw = noip_pw

    # start the meat of this, capturing interrupts and errors
    try:
        mainApp(bind=bind_addr, port=port)

    except (KeyboardInterrupt, SystemExit):
        log.warning('Keyboard interrupt intercepted.')
        sendEmail(
            sendTo=settings.noip_id,
            subject='NOIP-BOT stopped',
            body='NOIP-BOT stopped via Keyboard interrupt',
        )

    except RuntimeError as err:
        log.error(f'RuntimeError.\n{err}')
        sendEmail(
            sendTo=settings.noip_id,
            subject='NOIP-BOT Runtime exception',
            body=err,
        )
        raise

    except Exception as err:
        log.error(type(err))   # the exception instance
        log.error(err.args)    # arguments stored in .args
        log.error(err)         # print out the rest
        sendEmail(
            sendTo=settings.noip_id,
            subject='NOIP-BOT unknown exception',
            body=err,
        )
        raise

    finally:
        log.info('Shutting down scheduler task.')
        settings.scheduler.shutdown()

        log.info(f'Shutting down `{APP_NAME}`.')


if __name__ == '__main__':
    main()
