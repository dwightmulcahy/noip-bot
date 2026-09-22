import email
import imaplib
import logging
import re
import time
from email.header import decode_header


class VerificationCodeReader:
    """
    Polls a Gmail inbox over IMAP for a verification/2FA code email and
    extracts the code. Reuses the same GMAIL_ID / GMAIL_TOKEN (Gmail app
    password) credentials already used for outbound mail — app passwords
    work for both SMTP and IMAP.
    """

    def __init__(self, gmail_id: str, gmail_app_password: str, imap_host: str = 'imap.gmail.com'):
        self.gmail_id = gmail_id
        self.gmail_app_password = gmail_app_password
        self.imap_host = imap_host

    def _connect(self) -> imaplib.IMAP4_SSL:
        conn = imaplib.IMAP4_SSL(self.imap_host)
        conn.login(self.gmail_id, self.gmail_app_password)
        return conn

    def wait_for_code(self, sender: str = 'noip.com', subject_contains: str = None,
                       code_pattern: str = r'\b(\d{4,8})\b',
                       timeout: int = 120, poll_interval: int = 5,
                       mark_seen: bool = True) -> str:
        """Poll until a matching code email arrives, or `timeout` seconds elapse."""
        deadline = time.time() + timeout
        while True:
            code = self._search_latest(sender, subject_contains, code_pattern, mark_seen)
            if code:
                logging.info('Verification code found in email.')
                return code
            if time.time() >= deadline:
                logging.error('Timed out waiting for verification code email.')
                return None
            time.sleep(poll_interval)

    def _search_latest(self, sender, subject_contains, code_pattern, mark_seen) -> str:
        conn = self._connect()
        try:
            conn.select('INBOX')
            criteria = ['UNSEEN']
            if sender:
                criteria += ['FROM', sender]
            status, data = conn.search(None, *criteria)
            if status != 'OK' or not data or not data[0]:
                return None

            for msg_id in reversed(data[0].split()):  # newest first
                status, msg_data = conn.fetch(msg_id, '(RFC822)')
                if status != 'OK' or not msg_data or not msg_data[0]:
                    continue
                msg = email.message_from_bytes(msg_data[0][1])

                subject = self._decode_header(msg.get('Subject', ''))
                if subject_contains and subject_contains.lower() not in subject.lower():
                    continue

                match = re.search(code_pattern, self._get_body(msg))
                if match:
                    if mark_seen:
                        conn.store(msg_id, '+FLAGS', '\\Seen')
                    return match.group(1)
            return None
        finally:
            conn.logout()

    @staticmethod
    def _decode_header(value: str) -> str:
        parts = decode_header(value)
        return ''.join(
            part.decode(enc or 'utf-8', errors='ignore') if isinstance(part, bytes) else part
            for part, enc in parts
        )

    @staticmethod
    def _get_body(msg) -> str:
        if msg.is_multipart():
            for part in msg.walk():
                if part.get_content_type() in ('text/plain', 'text/html'):
                    payload = part.get_payload(decode=True)
                    if payload:
                        return payload.decode(part.get_content_charset() or 'utf-8', errors='ignore')
            return ''
        payload = msg.get_payload(decode=True)
        return payload.decode(msg.get_content_charset() or 'utf-8', errors='ignore') if payload else ''
