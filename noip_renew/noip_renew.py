#!/usr/bin/env python3
# Copyright 2017 loblab
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#       http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

# https://github.com/SeleniumHQ/selenium/tree/master/py
from random import uniform

import time
import subprocess
import sys
import os
import re
import types
from functools import total_ordering

# undetected-chromedriver (latest release on PyPI, 3.5.5) still does
# `from distutils.version import LooseVersion`, but distutils was removed
# from the stdlib entirely in Python 3.12+. Register a minimal stand-in
# before importing uc, rather than depending on setuptools' deprecated
# (and increasingly unavailable) local-distutils shim.
if 'distutils' not in sys.modules:
    try:
        import distutils.version  # noqa: F401 — real stdlib distutils (Python < 3.12)
    except ModuleNotFoundError:
        @total_ordering
        class _LooseVersion:
            def __init__(self, vstring):
                self.vstring = vstring
                self.version = [int(p) if p.isdigit() else p for p in re.split(r'[.\-]', vstring)]

            def __str__(self):
                return self.vstring

            def __repr__(self):
                return f"LooseVersion('{self.vstring}')"

            def __eq__(self, other):
                return self.version == getattr(other, 'version', other)

            def __lt__(self, other):
                return self.version < getattr(other, 'version', other)

        _distutils = types.ModuleType('distutils')
        _distutils_version = types.ModuleType('distutils.version')
        _distutils_version.LooseVersion = _LooseVersion
        _distutils.version = _distutils_version
        sys.modules['distutils'] = _distutils
        sys.modules['distutils.version'] = _distutils_version

import undetected_chromedriver as uc
from selenium.common.exceptions import TimeoutException, NoSuchElementException, StaleElementReferenceException
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.action_chains import ActionChains

# formatting for log messages
import logging
import datetime
from dateutil import parser as dateutil_parser
logging.basicConfig(
    format='%(asctime)s-%(levelname)s: %(message)s',
    datefmt='%d-%b %H:%M:%S',
    level=logging.INFO,
)

# human like typing
def humanType(elem, textToType):
    for c in textToType:
        elem.send_keys(c)
        time.sleep(uniform(0.05, 0.2))

def humanMouseMove(browser, elem):
    # Move via a nearby offset point first, then onto the element, rather
    # than jumping straight to it — a rough approximation of a natural
    # pointer path before clicking/focusing a field.
    action = ActionChains(browser)
    action.move_to_element_with_offset(elem, uniform(-15, 15), uniform(-10, 10))
    action.pause(uniform(0.05, 0.15))
    action.move_to_element(elem)
    action.pause(uniform(0.05, 0.2))
    action.click(elem)
    action.perform()

class Robot:
    # No hardcoded USER_AGENT: let Chrome send its own current UA string.
    # A stale spoofed UA (e.g. an old Firefox build) trips noip.com's
    # "your browser is out of date" interstitial.
    LOGIN_URL = 'https://www.noip.com/login'
    HOST_URL = 'https://my.noip.com'

    def __init__(self, username, password, debug, code_reader=None, confirm_buffer_days=5):
        self.debug = debug
        self.username = username
        self.password = password
        self.code_reader = code_reader  # emailServer.VerificationCodeReader, optional
        # Where debug/error screenshots get written. Defaults to the
        # current directory (unchanged behavior); set SCREENSHOT_DIR to
        # persist them elsewhere, e.g. a mounted volume in Docker.
        self.screenshot_dir = os.environ.get('SCREENSHOT_DIR', '.')
        os.makedirs(self.screenshot_dir, exist_ok=True)
        self.browser = self.init_browser()
        self.next_renewal = 0
        self.updatedHosts = []
        self.hosts = []
        self.host_expirations = {}  # {hostname: days_until_expiry}, all hosts with a visible countdown
        # Days before each host's 30-day mark to schedule the next check.
        # Self-calibrates: if a check finds a host isn't actually
        # confirmable yet despite being within this buffer, it's treated
        # as an overshoot (see update_hosts()) and this gets adjusted to
        # the real observed value once a host is caught being confirmable.
        self.confirm_buffer_days = confirm_buffer_days

    @staticmethod
    def _detect_chrome_major_version():
        # uc.Chrome()'s own auto-detection can guess a chromedriver version
        # that doesn't match what's actually installed (observed: fetched
        # a v151 driver against an installed v150 browser). Querying the
        # real binary directly avoids that mismatch.
        candidates = [
            os.environ.get('CHROME_BIN'),
            'google-chrome', 'google-chrome-stable', 'chromium', 'chromium-browser',
            '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',
        ]
        for candidate in filter(None, candidates):
            try:
                output = subprocess.run(
                    [candidate, '--version'], capture_output=True, text=True, timeout=10
                ).stdout
            except (OSError, subprocess.SubprocessError):
                continue
            match = re.search(r'(\d+)\.\d+\.\d+\.\d+', output)
            if match:
                return int(match.group(1))
        return None

    @staticmethod
    def init_browser(https_proxy=None):
        # undetected-chromedriver patches known CDP-level fingerprints that
        # plain Selenium exposes (beyond navigator.webdriver) — manual flags
        # like AutomationControlled/excludeSwitches don't reach these, which
        # is why noip.com's bot-detection/reCAPTCHA kept silently hanging
        # regardless of headless mode.
        options = uc.ChromeOptions()
        # added for Raspbian Buster 4.0+ versions.
        # Check https://www.raspberrypi.org/forums/viewtopic.php?t=258019 for reference.
        options.add_argument('--disable-features=VizDisplayCompositor')
        headless = os.environ.get('HEADLESS', 'true').lower() in ('1', 'true', 'yes')
        options.add_argument('--no-sandbox')  # need when run in docker
        options.add_argument('--window-size=1200,800')
        if 'https_proxy' in os.environ:
            options.add_argument(f'--proxy-server={os.environ["https_proxy"]}')

        # Cheap insurance against Chrome's native password-manager/autofill
        # suggestion bubble ever popping up and interfering.
        options.add_experimental_option('prefs', {
            'credentials_enable_service': False,
            'profile.password_manager_enabled': False,
            'profile.password_manager_leak_detection': False,
        })
        options.add_argument('--disable-save-password-bubble')

        version_main = Robot._detect_chrome_major_version()
        if version_main:
            logging.info(f'Detected installed Chrome major version: {version_main}')
        else:
            logging.warning('Could not detect installed Chrome version; letting uc guess (may mismatch).')

        browser = uc.Chrome(
            options=options,
            headless=headless,
            browser_executable_path=os.environ.get('CHROME_BIN'),
            version_main=version_main,
        )

        browser.set_page_load_timeout(90)    # Extended timeout for Raspberry Pi.
        return browser

    def screenshot(self, filename):
        """Save a screenshot into self.screenshot_dir (defaults to cwd;
        configurable via SCREENSHOT_DIR)."""
        self.browser.save_screenshot(os.path.join(self.screenshot_dir, filename))

    def login(self):
        logging.info(f'Opening {Robot.LOGIN_URL}...')
        self.browser.get(Robot.LOGIN_URL)
        if self.debug > 1:
            self.screenshot('debug1.png')

        logging.info('Logging in...')
        ele_usr = self.browser.find_element(By.XPATH, '//form[@id=\'clogs\']//input[@name=\'username\']')
        ele_pwd = self.browser.find_element(By.XPATH, '//form[@id=\'clogs\']//input[@name=\'password\']')

        humanMouseMove(self.browser, ele_usr)
        humanType(ele_usr, self.username)

        humanMouseMove(self.browser, ele_pwd)
        humanType(ele_pwd, self.password)

        # Verify before submitting rather than failing with a generic
        # "incorrect combination" on the result page.
        typed_pwd = self.browser.execute_script(
            "var e = document.querySelector(\"input[name='password']\"); return e ? e.value : null;"
        ) or ''
        if typed_pwd != self.password:
            logging.error(
                f'Password field contains {len(typed_pwd)} characters but the configured password is '
                f'{len(self.password)} characters — they don\'t match after typing.'
            )
            raise Exception('Password field does not match configured password after typing; aborting login.')

        login_button = self.browser.find_element(By.ID, 'clogs-captcha-button')
        humanMouseMove(self.browser, login_button)

        if '/login' not in self.browser.current_url:
            # humanMouseMove's own ActionChains click already submitted the
            # form and we've navigated away — that's success, not a
            # failure. Clicking again on a page that no longer has this
            # form would be wrong.
            logging.info(f'Logged in (now at {self.browser.current_url}).')
        else:
            login_button.click()
            if self.debug > 1:
                time.sleep(1)
                self.screenshot('debug2.png')

        # The login button's onclick generates a reCAPTCHA v3 token
        # asynchronously *before* actually submitting the form, so the
        # navigation away from /login can lag well behind the click.
        # Proceeding before that finishes (e.g. straight to browser.get()
        # elsewhere) can cut the in-flight submission off entirely, with
        # no visible error — it just silently never logs in.
        try:
            WebDriverWait(self.browser, 30).until(
                lambda d: '/login' not in d.current_url
                or d.find_elements(By.CSS_SELECTOR, '#otp-input input')
            )
        except TimeoutException:
            self.screenshot('login_stuck.png')
            raise Exception(
                f'Still on the login page 30s after submitting (current URL: {self.browser.current_url}). '
                f'Likely rejected silently (e.g. reCAPTCHA score) rather than a wrong-password error.'
            )

        self._handle_verification_code_if_present()

    def _handle_verification_code_if_present(self):
        """
        noip.com may challenge with an emailed 6-digit code (form#challenge_form
        at /2fa/verify). The code is split across six single-digit <input>
        boxes inside #otp-input; the page's own JS auto-submits the form once
        all six are filled, so no submit click is needed in the normal case.
        """
        try:
            code_inputs = WebDriverWait(self.browser, 5).until(
                EC.presence_of_all_elements_located((By.CSS_SELECTOR, '#otp-input input'))
            )
        except TimeoutException:
            return  # no verification-code challenge this time

        logging.info('Verification code challenge detected; checking email...')
        if not self.code_reader:
            self.screenshot('verification_code_needed.png')
            raise Exception('Verification code required but no code_reader configured.')

        code = self.code_reader.wait_for_code(sender='noip.com', timeout=120)
        if not code:
            self.screenshot('verification_code_timeout.png')
            raise Exception('Timed out waiting for verification code email.')

        for box, digit in zip(code_inputs, code):
            box.send_keys(digit)

        # The page auto-submits once all boxes are filled; fall back to the
        # manual "Verify" button only if that somehow didn't navigate away.
        try:
            WebDriverWait(self.browser, 10).until(EC.staleness_of(code_inputs[0]))
        except TimeoutException:
            try:
                self.browser.find_element(By.ID, 'ManualSubmitMfa').click()
            except NoSuchElementException:
                pass

        if self.debug > 1:
            time.sleep(1)
            self.screenshot('debug3.png')

    def open_hosts_page(self):
        logging.info(f'Opening {Robot.HOST_URL}...')
        step = 'loading dashboard'
        try:
            self.browser.get(Robot.HOST_URL)

            step = "finding the 'Hostnames' link"
            hostnames_link = WebDriverWait(self.browser, 15).until(
                EC.element_to_be_clickable(
                    (By.XPATH, "//a[contains(@href,'/dns/records')][contains(@class,'list-group-header')]")
                )
            )

            step = "clicking 'Hostnames' / waiting for URL to change"
            hostnames_link.click()
            WebDriverWait(self.browser, 15).until(EC.url_contains('/dns/records'))

            step = 'waiting for the records page to finish loading'
            WebDriverWait(self.browser, 15).until(
                lambda d: d.execute_script('return document.readyState') == 'complete'
            )
        except TimeoutException as e:
            self.screenshot('timeout.png')
            logging.info(f'Timeout while {step}: {str(e)}')

    def update_host(self, host_id, host_name):
        logging.info(f'Confirming renewal for {host_name}')
        selector = (By.CSS_SELECTOR, f"button[hx-get*='/ajax/host/{host_id}/touch']")
        for attempt in (1, 2):
            try:
                confirm_button = WebDriverWait(self.browser, 10).until(EC.element_to_be_clickable(selector))
                confirm_button.click()
                break
            except (TimeoutException, StaleElementReferenceException) as e:
                if attempt == 2:
                    raise
                logging.info(f'Retrying confirm click for {host_name} after: {str(e)}')
                time.sleep(2)
        time.sleep(2)
        self.screenshot(f'{host_name}_confirmed.png')

    @staticmethod
    def _extract_host_id(confirm_button):
        hx_get = confirm_button.get_attribute('hx-get') or ''
        match = re.search(r'/ajax/host/(\d+)/touch', hx_get)
        return match.group(1) if match else None

    def get_host_name(self, host_id):
        # Each hostname's row is a div.zone-record with data-name (host part)
        # and data-zone (domain part), and data-label="host=<id>" linking it
        # to the same id used in the confirm button's /ajax/host/<id>/touch.
        if not host_id:
            return 'unknown-host'
        try:
            row = self.browser.find_element(By.XPATH, f"//div[contains(@data-label,'host={host_id}')]")
            name, zone = row.get_attribute('data-name'), row.get_attribute('data-zone')
            if name and zone:
                return f'{name}.{zone}'
        except NoSuchElementException:
            pass
        return f'host-{host_id}'

    def get_hosts(self):
        self.screenshot('hosts.png')
        # Only hosts actually needing renewal show a confirm banner, so an
        # empty list here just means nothing is due yet — not an error.
        # Returns (host_id, host_name) pairs rather than WebElements, since
        # the confirm button is re-located fresh right before each click
        # (see update_host) to avoid stale-element issues from htmx swaps.
        confirm_buttons = self.browser.find_elements(By.CSS_SELECTOR, "button[hx-get*='/ajax/host/']")
        host_list = []
        for button in confirm_buttons:
            host_id = self._extract_host_id(button)
            host_list.append((host_id, self.get_host_name(host_id)))
        return host_list

    def get_expiration_days_by_host(self):
        # Every hostname row shows a warning icon with title="Expires in N
        # days" once it's within its renewal window, independent of whether
        # a confirm banner is currently on screen for it. Used only for
        # scheduling the next check, not for deciding what to confirm.
        result = {}
        for row in self.browser.find_elements(By.CSS_SELECTOR, 'div.zone-record[data-label]'):
            popovers = row.find_elements(
                By.XPATH, ".//span[contains(@class,'popover-info')][contains(@title,'Expires in')]"
            )
            if not popovers:
                continue
            match = re.search(r'\d+', popovers[0].get_attribute('title') or '')
            if not match:
                continue
            name, zone = row.get_attribute('data-name'), row.get_attribute('data-zone')
            if name and zone:
                result[f'{name}.{zone}'] = int(match.group(0))
        return result

    def log_all_records(self):
        """Log every hostname record's name and last-updated timestamp,
        regardless of whether it's near expiration — for visibility into
        what's on the account each run."""
        rows = self.browser.find_elements(By.CSS_SELECTOR, 'div.zone-record[data-label]')
        if not rows:
            logging.info('No records found on the page.')
            return
        logging.info(f'Found {len(rows)} record(s):')
        for row in rows:
            name, zone = row.get_attribute('data-name'), row.get_attribute('data-zone')
            last_update = row.get_attribute('data-update') or 'unknown'
            hostname = f'{name}.{zone}' if name and zone else '(unknown host)'
            logging.info(f'  {hostname} — last updated: {last_update}')

    def get_last_update_by_host(self):
        """Parse each record's data-update timestamp (e.g. 'Jul 28, 2026
        15:51:01') into a date, keyed by hostname. Used to track each
        host's age against its 30-day free-hostname cycle, independent of
        whatever countdown (if any) the site itself is currently showing."""
        result = {}
        for row in self.browser.find_elements(By.CSS_SELECTOR, 'div.zone-record[data-label]'):
            name, zone = row.get_attribute('data-name'), row.get_attribute('data-zone')
            last_update_str = row.get_attribute('data-update')
            if not (name and zone and last_update_str):
                continue
            try:
                result[f'{name}.{zone}'] = dateutil_parser.parse(last_update_str).date()
            except (ValueError, TypeError):
                continue
        return result

    def update_hosts(self):
        self.open_hosts_page()
        time.sleep(1)

        self.log_all_records()

        last_update_by_host = self.get_last_update_by_host()
        today = datetime.date.today()
        days_until_30 = {host: 30 - (today - dt).days for host, dt in last_update_by_host.items()}

        exp_by_host = self.get_expiration_days_by_host()

        self.hosts = self.get_hosts()
        if not self.hosts:
            logging.info('No hostnames currently need renewal confirmation.')
        for host_id, host_name in self.hosts:
            logging.info(f'...{host_name} expires in {exp_by_host.get(host_name, "?")} days')
            self.updatedHosts.append(host_name)
            self.update_host(host_id, host_name)
            # Confirming resets the ~30-day free-host cycle.
            exp_by_host[host_name] = exp_by_host.get(host_name, 0) + 30
        self.screenshot('results.png')

        self.host_expirations = exp_by_host

        # Adaptive scheduling: a host is "expected confirmable" once it's
        # within confirm_buffer_days of its 30-day mark. If one is there but
        # wasn't actually confirmable, the buffer overshot (checked too
        # early) — warn and retry daily rather than waiting a full cycle.
        # Once a host IS caught being confirmable, adopt the days remaining
        # at that moment as the calibrated buffer going forward.
        expected_hosts = {h for h, d in days_until_30.items() if d <= self.confirm_buffer_days}
        overshot_hosts = expected_hosts - set(self.updatedHosts)

        if overshot_hosts:
            for host in overshot_hosts:
                logging.warning(
                    f'Expected {host} to be confirmable within a {self.confirm_buffer_days}-day buffer '
                    f'({days_until_30[host]} day(s) left on its 30-day mark), but it wasn\'t actually '
                    f'confirmable yet. Buffer may be too large; checking again tomorrow.'
                )
            self.next_renewal = 1
        else:
            if self.updatedHosts:
                observed = [days_until_30[h] for h in self.updatedHosts if h in days_until_30]
                if observed:
                    learned = max(observed)
                    if learned != self.confirm_buffer_days:
                        logging.info(
                            f'Learned confirmation buffer: hosts become confirmable {learned} day(s) before '
                            f'their 30-day mark (was assuming {self.confirm_buffer_days}). Using {learned} '
                            f'from now on.'
                        )
                        self.confirm_buffer_days = learned
            self.next_renewal = (
                max(min(days_until_30.values()) - self.confirm_buffer_days, 1) if days_until_30 else 0
            )
        return True

    def run(self):
        # TODO: these need to raise exceptions so `main` can catch vs an int-rc...
        rc = 0
        logging.info(f'Debug level: {self.debug}')
        try:
            self.login()
            if not self.update_hosts():
                rc = 3
        except Exception as e:
            logging.info(str(e))
            self.screenshot('exception.png')
            rc = 2
        finally:
            self.browser.quit()
        return rc


def main(argv=None):
    noip_username, noip_password, debug,  = get_args_values(argv)
    return (Robot(noip_username, noip_password, debug)).run()


def get_args_values(argv):
    if argv is None:
        argv = sys.argv
    if len(argv) < 3:
        print(f'Usage: {argv[0]} <noip_username> <noip_password> [<debug-level>] ')
        sys.exit(1)

    noip_username = argv[1]
    noip_password = argv[2]
    debug = 1
    if len(argv) > 3:
        debug = int(argv[3])
    return noip_username, noip_password, debug


if __name__ == '__main__':
    sys.exit(main())
