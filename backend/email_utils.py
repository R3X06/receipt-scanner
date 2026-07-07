"""Transactional email (verification + password reset) via Resend's REST API.

Deliberately uses `requests` directly instead of the `resend` SDK — `requests`
is already a dependency, and the API surface needed here is one POST, so a new
SDK dependency wasn't worth adding.

Fails loud to the logs, never raises into the caller: a broken email provider
should not 500 a signup or a password-reset request. Callers get a bool back
and decide what (if anything) to tell the user.
"""
import os

import requests

from logging_config import logger

RESEND_API_KEY = os.getenv("RESEND_API_KEY")
FROM_EMAIL = os.getenv("FROM_EMAIL", "KALLA <onboarding@resend.dev>")
FRONTEND_URL = os.getenv("FRONTEND_URL", "http://localhost:5173")


def send_email(to: str, subject: str, html: str) -> bool:
    if not RESEND_API_KEY:
        # Expected in local dev unless you've set up a Resend account. Logged
        # at warning (not error) so it doesn't look like a production issue.
        logger.warning("email_not_sent_no_api_key", extra={"to": to, "subject": subject})
        return False
    try:
        resp = requests.post(
            "https://api.resend.com/emails",
            headers={"Authorization": f"Bearer {RESEND_API_KEY}"},
            json={"from": FROM_EMAIL, "to": [to], "subject": subject, "html": html},
            timeout=10,
        )
        if resp.status_code >= 400:
            logger.error(
                "email_send_failed",
                extra={"to": to, "status": resp.status_code, "body": resp.text[:300]},
            )
            return False
        return True
    except requests.RequestException:
        logger.error("email_send_exception", exc_info=True, extra={"to": to})
        return False


def send_verification_email(to: str, token: str) -> bool:
    link = f"{FRONTEND_URL}/verify-email?token={token}"
    html = (
        f"<p>Confirm your KALLA account by clicking the link below:</p>"
        f"<p><a href='{link}'>{link}</a></p>"
        f"<p>This link expires in 24 hours. If you didn't sign up for KALLA, "
        f"you can ignore this email.</p>"
    )
    return send_email(to, "Verify your KALLA email", html)


def send_password_reset_email(to: str, token: str) -> bool:
    link = f"{FRONTEND_URL}/reset-password?token={token}"
    html = (
        f"<p>Reset your KALLA password by clicking the link below:</p>"
        f"<p><a href='{link}'>{link}</a></p>"
        f"<p>This link expires in 30 minutes. If you didn't request this, "
        f"you can ignore this email — your password won't change.</p>"
    )
    return send_email(to, "Reset your KALLA password", html)