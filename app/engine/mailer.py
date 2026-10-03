# Copyright 2026 Andrei Maltsev (Rawanga)
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
"""
mailer.py — optional e-mail delivery of trade/trend alerts via the user's own SMTP.

This is a second notification channel alongside Telegram. The user points it at
their own mailbox (SMTP host/port/login) and receives alerts as e-mails TO
THEMSELVES. No third-party service is involved: only the standard library.

This is deliberately NOT a bulk-mailer / newsletter tool. It is a personal
alert pipe, and the following guards are enforced in code:
  * exactly ONE recipient, taken from the saved settings (no lists, no
    comma/semicolon-separated addresses, no Bcc/Cc);
  * the recipient is the mailbox the user configured — never taken from alert
    text or any request payload;
  * subject/body size caps.

There is intentionally NO rate limit: alerts are per-signal and must never be
dropped during active trading (a missed signal is worse than an extra e-mail).

Configuration is stored with the other trading secrets (encrypted):
  smtp_host, smtp_port, smtp_user, smtp_pass, smtp_tls, notify_email
"""
from __future__ import annotations

import asyncio
import logging
import re
import smtplib
import ssl
from email.message import EmailMessage
from email.utils import formatdate, make_msgid

log = logging.getLogger("tv.mailer")

# smtplib/ssl are blocking — run them in a worker thread so the event loop is not stalled.
_SEND_TIMEOUT = 20

# ── Guards (personal alert pipe, not a bulk sender) ─────────────────────────
# NOTE: no rate limit on purpose — every signal must be delivered.
MAX_SUBJECT = 200
MAX_BODY = 20_000

# Single, plain e-mail address. Rejects lists ("a@x, b@y"), display names with
# commas, and anything with whitespace/angle-brackets.
_EMAIL_RE = re.compile(r"^[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}$")


def _valid_single_recipient(addr: str) -> bool:
    a = (addr or "").strip()
    if not a or "," in a or ";" in a or "<" in a or ">" in a or " " in a:
        return False
    return bool(_EMAIL_RE.match(a))


def _plain_text(html_text: str) -> str:
    """Crude HTML→text for the plain-text part (keeps e-mails readable anywhere)."""
    txt = re.sub(r"<br\s*/?>", "\n", html_text or "", flags=re.IGNORECASE)
    txt = re.sub(r"</?b>", "", txt, flags=re.IGNORECASE)
    txt = re.sub(r"<[^>]+>", "", txt)
    return txt.strip()


def _send_sync(cfg: dict, subject: str, body: str) -> dict:
    host = (cfg.get("host") or "").strip()
    if not host:
        return {"ok": False, "error": "smtp host not set"}
    to_addr = (cfg.get("to") or "").strip()
    if not to_addr:
        return {"ok": False, "error": "recipient e-mail not set"}
    # Guard #1: exactly one valid recipient, from settings only.
    if not _valid_single_recipient(to_addr):
        return {"ok": False, "error": "invalid or multiple recipients (exactly one address required)"}
    try:
        port = int(cfg.get("port") or 587)
    except (TypeError, ValueError):
        port = 587
    user = (cfg.get("user") or "").strip()
    pwd = cfg.get("password") or ""
    use_tls = bool(cfg.get("tls", True))
    from_addr = (cfg.get("from") or user or to_addr).strip()
    if not _valid_single_recipient(from_addr):
        from_addr = user if _valid_single_recipient(user) else to_addr

    # Guard #2: size caps.
    subject = (subject or "Rawanga Trading Desk alert")[:MAX_SUBJECT]
    body = body or ""
    if len(body) > MAX_BODY:
        body = body[:MAX_BODY] + "\n…(truncated)"

    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = from_addr
    msg["To"] = to_addr          # single recipient, no Cc/Bcc ever
    msg["Date"] = formatdate(localtime=True)
    msg["Message-ID"] = make_msgid(domain=(from_addr.split("@")[-1] or "localhost"))
    msg.set_content(_plain_text(body))
    msg.add_alternative(body, subtype="html")

    try:
        if port == 465:
            # Implicit TLS (SMTPS).
            ctx = ssl.create_default_context()
            with smtplib.SMTP_SSL(host, port, timeout=_SEND_TIMEOUT, context=ctx) as s:
                if user:
                    s.login(user, pwd)
                s.send_message(msg)
        else:
            with smtplib.SMTP(host, port, timeout=_SEND_TIMEOUT) as s:
                s.ehlo()
                if use_tls:
                    s.starttls(context=ssl.create_default_context())
                    s.ehlo()
                if user:
                    s.login(user, pwd)
                s.send_message(msg)
        return {"ok": True, "to": to_addr}
    except Exception as e:  # noqa: BLE001
        log.warning("e-mail send failed to %s: %s", to_addr, e)
        return {"ok": False, "error": str(e)}


def _send_guarded(cfg: dict, subject: str, body: str) -> dict:
    # No rate limiting: every alert is delivered as-is.
    return _send_sync(cfg, subject, body)


async def send_email(cfg: dict, subject: str, body: str) -> dict:
    """Send one alert e-mail to the single configured recipient.

    `cfg` carries host/port/user/password/tls/to/from. The recipient is always
    the user's own address from settings — never a list and never caller-supplied.
    """
    return await asyncio.to_thread(_send_guarded, cfg, subject, body)
