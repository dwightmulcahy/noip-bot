#!/usr/bin/env python3
# No-IP Renewal Bot
# Originally derived from https://github.com/loblab/noip-renew
# Original work Copyright 2017 loblab
# Modifications and current version Copyright 2026 Dwight Mulcahy
# This file has been substantially modified from the original work.
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

from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
from selenium.common.exceptions import TimeoutException, NoSuchElementException, StaleElementReferenceException
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

import time
import sys
import os
import re
from datetime import datetime, timedelta, timezone


# formatting for log messages
import logging
from logging_config import configure_logging
from state_store import StateStore

SCREENSHOT_DIR = os.environ.get('SCREENSHOT_DIR', os.path.join(os.getcwd(), 'screenshots'))
os.makedirs(SCREENSHOT_DIR, exist_ok=True)


def screenshot_path(filename):
    return os.path.join(SCREENSHOT_DIR, filename)


def renewal_is_verified(confirm_buttons, before_update, after_update):
    return not confirm_buttons and bool(after_update) and after_update != before_update


configure_logging()
log = logging.getLogger(__name__)

# human like typing
def humanType(elem, textToType):
    for c in textToType:
        elem.send_keys(c)
        time.sleep(uniform(0.05, 0.2))

class Robot:
    # No hardcoded USER_AGENT: let Chrome send its own current UA string.
    # A stale spoofed UA (e.g. an old Firefox build) trips noip.com's
    # "your browser is out of date" interstitial.
    LOGIN_URL = 'https://www.noip.com/login'
    HOST_URL = 'https://my.noip.com'

    def __init__(
        self, username, password, debug, code_reader=None, state_store=None,
        dry_run=False
    ):
        self.debug = debug
        self.dry_run = bool(dry_run)
        self.username = username
        self.password = password
        self.code_reader = code_reader  # emailServer.VerificationCodeReader, optional
        self.state_store = state_store or StateStore()
        try:
            self.browser = self.init_browser()
        except Exception as exc:
            self.state_store.record_failure(exc)
            raise
        self.next_renewal = 0
        self.updatedHosts = []
        self.wouldUpdateHosts = []
        self.hosts = []
        self.host_expirations = {}  # {hostname: days_until_expiry}, all hosts with a visible countdown

    @staticmethod
    def init_browser(https_proxy=None):
        options = webdriver.ChromeOptions()
        # added for Raspbian Buster 4.0+ versions. 
        # Check https://www.raspberrypi.org/forums/viewtopic.php?t=258019 for reference.
        options.add_argument('--disable-features=VizDisplayCompositor')
        if os.environ.get('HEADLESS', 'false').lower() in ('1', 'true', 'yes', 'on'):
            options.add_argument('--headless=new')
        options.add_argument('--no-sandbox')  # need when run in docker
        options.add_argument('--disable-dev-shm-usage')
        options.add_argument('--remote-debugging-pipe')
        options.add_argument('--window-size=1200,800')
        # Mask Selenium automation fingerprints so noip.com doesn't detect
        # this as a bot and serve its "browser is out of date" block page.
        options.add_argument('--disable-blink-features=AutomationControlled')
        options.add_experimental_option('excludeSwitches', ['enable-automation'])
        options.add_experimental_option('useAutomationExtension', False)
        if 'CHROME_BIN' in os.environ:
            options.binary_location = os.environ['CHROME_BIN']
        if 'https_proxy' in os.environ:
            options.add_argument(f'--proxy-server={os.environ["https_proxy"]}')

        driver_path = os.environ.get('CHROMEDRIVER_BIN', '/usr/bin/chromedriver')
        driver_log = os.environ.get(
            'CHROMEDRIVER_LOG',
            os.path.join(os.path.dirname(SCREENSHOT_DIR), 'chromedriver.log'),
        )
        os.makedirs(os.path.dirname(os.path.abspath(driver_log)), exist_ok=True)
        if not os.path.isfile(driver_path):
            os.environ['WDM_LOG_LEVEL'] = '0'
            driver_path = ChromeDriverManager().install()
            logging.getLogger('webdriver_manager').setLevel(logging.ERROR)
        log.info(
            'Starting Chromium',
            extra={
                'event': 'browser_starting',
                'chrome_binary': options.binary_location or 'auto',
                'chromedriver': driver_path,
                'headless': '--headless=new' in options.arguments,
                'chromedriver_log': driver_log,
            },
        )
        service = Service(
            executable_path=driver_path,
            log_output=driver_log,
            service_args=['--verbose'],
        )
        browser = webdriver.Chrome(service=service, options=options)

        # Belt-and-suspenders: overwrite navigator.webdriver on every new
        # document, since some sites check it directly regardless of the
        # AutomationControlled flag above.
        browser.execute_cdp_cmd('Page.addScriptToEvaluateOnNewDocument', {
            'source': 'Object.defineProperty(navigator, "webdriver", {get: () => undefined})'
        })

        browser.set_page_load_timeout(90)    # Extended timeout for Raspberry Pi.
        return browser

    def login(self):
        log.info('Opening login page', extra={'event': 'navigation', 'url': Robot.LOGIN_URL})
        self.browser.get(Robot.LOGIN_URL)
        if self.debug > 1:
            self.browser.save_screenshot(screenshot_path('debug1.png'))

        log.info('Logging in', extra={'event': 'login_started'})
        ele_usr = self.browser.find_element(By.XPATH, '//form[@id=\'clogs\']//input[@name=\'username\']')
        ele_pwd = self.browser.find_element(By.XPATH, '//form[@id=\'clogs\']//input[@name=\'password\']')

        humanType(ele_usr, self.username)
        humanType(ele_pwd, self.password)
        # ele_pwd.send_keys(base64.b64decode(self.password).decode('utf-8'))
        # self.browser.find_element_by_name("Login").click()
        self.browser.find_element(By.ID, 'clogs-captcha-button').click()
        if self.debug > 1:
            time.sleep(1)
            self.browser.save_screenshot(screenshot_path('debug2.png'))

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

        log.info('Verification code challenge detected', extra={'event': 'verification_required'})
        if not self.code_reader:
            self.browser.save_screenshot(screenshot_path('verification_code_needed.png'))
            raise Exception('Verification code required but no code_reader configured.')

        code = self.code_reader.wait_for_code(sender='noip.com', timeout=120)
        if not code:
            self.browser.save_screenshot(screenshot_path('verification_code_timeout.png'))
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
            self.browser.save_screenshot(screenshot_path('debug3.png'))

    def open_hosts_page(self):
        log.info('Opening host records', extra={'event': 'navigation', 'url': Robot.HOST_URL})
        try:
            self.browser.get(Robot.HOST_URL)
            hostnames_link = WebDriverWait(self.browser, 15).until(
                EC.element_to_be_clickable(
                    (By.XPATH, "//a[@href='/dns/records'][contains(@class,'list-group-header')]")
                )
            )
            hostnames_link.click()
            WebDriverWait(self.browser, 15).until(EC.url_contains('/dns/records'))
            WebDriverWait(self.browser, 15).until(
                lambda d: d.execute_script('return document.readyState') == 'complete'
            )
        except TimeoutException as e:
            self.browser.save_screenshot(screenshot_path('timeout.png'))
            log.error('Timed out opening host records', extra={'event': 'navigation_failed'})
            raise RuntimeError('No-IP host records page did not load') from e

    def _get_host_row(self, host_id):
        return self.browser.find_element(
            By.XPATH, f"//div[contains(@data-label,'host={host_id}')]"
        )

    def _get_data_update(self, host_id):
        value = self._get_host_row(host_id).get_attribute('data-update')
        if not value:
            raise RuntimeError(f'Host {host_id} has no data-update timestamp')
        return value

    def update_host(self, host_id, host_name):
        before_update = self._get_data_update(host_id)
        log.info(
            'Confirming renewal',
            extra={'event': 'renewal_started', 'host': host_name, 'host_id': host_id,
                   'data_update_before': before_update},
        )
        selector = (By.CSS_SELECTOR, f"button[hx-get*='/ajax/host/{host_id}/touch']")
        for attempt in (1, 2):
            try:
                confirm_button = WebDriverWait(self.browser, 10).until(EC.element_to_be_clickable(selector))
                confirm_button.click()
                break
            except (TimeoutException, StaleElementReferenceException) as e:
                if attempt == 2:
                    raise
                log.warning(
                    'Retrying renewal click',
                    extra={'event': 'renewal_click_retry', 'host': host_name, 'attempt': attempt},
                )
                time.sleep(2)

        def renewal_completed(driver):
            buttons = driver.find_elements(*selector)
            try:
                after_update = self._get_data_update(host_id)
            except (NoSuchElementException, StaleElementReferenceException):
                return False
            if renewal_is_verified(buttons, before_update, after_update):
                return after_update
            return False

        try:
            after_update = WebDriverWait(self.browser, 20).until(renewal_completed)
        except TimeoutException as exc:
            self.browser.save_screenshot(screenshot_path(f'{host_name}_verification_failed.png'))
            raise RuntimeError(
                f'Renewal verification failed for {host_name}: confirmation control remained '
                f'or data-update did not change from {before_update!r}'
            ) from exc

        self.browser.save_screenshot(screenshot_path(f'{host_name}_confirmed.png'))
        log.info(
            'Renewal verified',
            extra={'event': 'renewal_verified', 'host': host_name, 'host_id': host_id,
                   'data_update_before': before_update, 'data_update_after': after_update},
        )
        return before_update, after_update

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
            row = self._get_host_row(host_id)
            name, zone = row.get_attribute('data-name'), row.get_attribute('data-zone')
            if name and zone:
                return f'{name}.{zone}'
        except NoSuchElementException:
            pass
        return f'host-{host_id}'

    def get_hosts(self):
        self.browser.save_screenshot(screenshot_path('hosts.png'))
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

    def get_host_inventory(self):
        inventory = {}
        renewable_host_ids = {
            self._extract_host_id(button)
            for button in self.browser.find_elements(
                By.CSS_SELECTOR, "button[hx-get*='/ajax/host/']"
            )
        }
        for row in self.browser.find_elements(By.CSS_SELECTOR, 'div.zone-record[data-label]'):
            name = row.get_attribute('data-name')
            zone = row.get_attribute('data-zone')
            if not name or not zone:
                continue
            hostname = f'{name}.{zone}'
            label = row.get_attribute('data-label') or ''
            host_id_match = re.search(r'host=(\d+)', label)
            expiration = None
            popovers = row.find_elements(
                By.XPATH, ".//span[contains(@class,'popover-info')][contains(@title,'Expires in')]"
            )
            if popovers:
                expiration_match = re.search(r'\d+', popovers[0].get_attribute('title') or '')
                if expiration_match:
                    expiration = int(expiration_match.group(0))
            inventory[hostname] = {
                'host_id': host_id_match.group(1) if host_id_match else None,
                'data_update': row.get_attribute('data-update'),
                'expires_in_days': expiration,
                'renewal_available': (
                    bool(host_id_match) and host_id_match.group(1) in renewable_host_ids
                ),
            }
        return inventory

    def update_hosts(self):
        self.open_hosts_page()
        time.sleep(1)

        inventory = self.get_host_inventory()
        self.state_store.record_inventory(inventory)
        exp_by_host = {
            hostname: details['expires_in_days']
            for hostname, details in inventory.items()
            if details['expires_in_days'] is not None
        }

        self.hosts = self.get_hosts()
        if not self.hosts:
            log.info('No hostnames need renewal', extra={'event': 'renewal_not_required'})
        for host_id, host_name in self.hosts:
            expires_in = exp_by_host.get(host_name)
            if self.dry_run:
                self.wouldUpdateHosts.append(host_name)
                log.info(
                    'Dry run would renew hostname',
                    extra={
                        'event': 'renewal_would_run',
                        'host': host_name,
                        'host_id': host_id,
                        'expires_in_days': expires_in,
                        'dry_run': True,
                    },
                )
                continue
            before_update, after_update = self.update_host(host_id, host_name)
            self.updatedHosts.append(host_name)
            # Confirming resets the ~30-day free-host cycle.
            exp_by_host[host_name] = (expires_in or 0) + 30
            self.state_store.record_host(
                host_name, before_update, after_update, exp_by_host[host_name]
            )
        self.browser.save_screenshot(screenshot_path('results.png'))

        refreshed_inventory = self.get_host_inventory()
        self.state_store.record_inventory(refreshed_inventory)
        self.state_store.record_would_renew(self.wouldUpdateHosts)

        self.host_expirations = exp_by_host
        self.next_renewal = min(exp_by_host.values()) if exp_by_host else 0
        return True

    def run(self):
        self.state_store.record_run_started(self.dry_run)
        log.info(
            'Renewal run started',
            extra={'event': 'run_started', 'debug': self.debug, 'dry_run': self.dry_run},
        )
        try:
            self.login()
            self.update_hosts()
            next_check = (
                datetime.now(timezone.utc) + timedelta(days=self.next_renewal)
            ).isoformat() if self.next_renewal else None
            self.state_store.record_success(
                next_check, self.host_expirations, self.next_renewal
            )
            log.info(
                'Renewal run succeeded',
                extra={'event': 'run_succeeded', 'updated_hosts': self.updatedHosts,
                       'would_renew': self.wouldUpdateHosts,
                       'next_renewal_days': self.next_renewal,
                       'dry_run': self.dry_run},
            )
        except Exception as exc:
            self.state_store.record_failure(exc)
            log.exception('No-IP renewal run failed', extra={'event': 'run_failed'})
            self.browser.save_screenshot(screenshot_path('exception.png'))
            raise
        finally:
            self.browser.quit()
        return 0


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
