"""Transactional email via Resend API or SMTP (async wrapper)."""
import asyncio
import logging
import smtplib
from email.message import EmailMessage

import httpx

from app.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()


def _smtp_configured() -> bool:
    return bool(settings.SMTP_HOST and settings.SMTP_FROM)


def _resend_configured() -> bool:
    return bool(settings.RESEND_API_KEY)


def _send_sync(to_email: str, subject: str, text_body: str, html_body: str | None = None) -> None:
    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = settings.SMTP_FROM
    msg["To"] = to_email
    msg.set_content(text_body)
    if html_body:
        msg.add_alternative(html_body, subtype="html")

    if settings.SMTP_USE_TLS:
        with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT, timeout=30) as smtp:
            smtp.starttls()
            if settings.SMTP_USER:
                smtp.login(settings.SMTP_USER, settings.SMTP_PASSWORD)
            smtp.send_message(msg)
    else:
        with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT, timeout=30) as smtp:
            if settings.SMTP_USER:
                smtp.login(settings.SMTP_USER, settings.SMTP_PASSWORD)
            smtp.send_message(msg)


def _send_via_resend(to_email: str, subject: str, text_body: str, html_body: str | None = None) -> None:
    payload: dict = {
        "from": settings.RESEND_FROM or settings.SMTP_FROM or "noreply@llm-guardrails.dev",
        "to": [to_email],
        "subject": subject,
        "text": text_body,
    }
    if html_body:
        payload["html"] = html_body

    resp = httpx.post(
        "https://api.resend.com/emails",
        headers={"Authorization": f"Bearer {settings.RESEND_API_KEY}"},
        json=payload,
        timeout=30,
    )
    resp.raise_for_status()


async def send_email(to_email: str, subject: str, text_body: str, html_body: str | None = None) -> None:
    if _resend_configured():
        await asyncio.to_thread(_send_via_resend, to_email, subject, text_body, html_body)
    elif _smtp_configured():
        await asyncio.to_thread(_send_sync, to_email, subject, text_body, html_body)
    else:
        logger.warning(
            "email.not_configured to=%s subject=%s",
            to_email,
            subject,
        )
        return


async def send_verification_email(to_email: str, verify_url: str) -> None:
    subject = f"Confirm your {settings.APP_NAME} account"
    text = (
        f"Welcome to {settings.APP_NAME}.\n\n"
        f"Confirm your email by opening this link (valid for {settings.EMAIL_VERIFICATION_EXPIRE_HOURS} hours):\n"
        f"{verify_url}\n\n"
        "If you did not create an account, you can ignore this email."
    )
    html = (
        f"<p>Welcome to <strong>{settings.APP_NAME}</strong>.</p>"
        f"<p><a href=\"{verify_url}\">Confirm your email address</a></p>"
        f"<p>This link expires in {settings.EMAIL_VERIFICATION_EXPIRE_HOURS} hours.</p>"
        f"<p style=\"color:#666;font-size:12px\">If you did not sign up, ignore this message.</p>"
    )
    await send_email(to_email, subject, text, html)


async def send_low_balance_email(to_email: str, balance: int, app_url: str) -> None:
    subject = f"Low token balance — {settings.APP_NAME}"
    text = (
        f"Your {settings.APP_NAME} token balance is running low ({balance:,} tokens remaining).\n\n"
        f"Top up at: {app_url}\n\n"
        "Purchase a plan to keep your gateway running without interruption."
    )
    html = (
        f"<p>Your <strong>{settings.APP_NAME}</strong> token balance is running low.</p>"
        f"<p><strong>{balance:,} tokens remaining.</strong></p>"
        f"<p><a href=\"{app_url}\">Top up your balance</a></p>"
        f"<p style=\"color:#666;font-size:12px\">You received this because your balance dropped below 10% of your initial allocation.</p>"
    )
    await send_email(to_email, subject, text, html)


async def send_password_reset_email(to_email: str, reset_url: str) -> None:
    subject = f"Reset your {settings.APP_NAME} password"
    text = (
        f"Reset your password using this link (valid for {settings.PASSWORD_RESET_EXPIRE_HOURS} hour(s)):\n"
        f"{reset_url}\n\n"
        "If you did not request a reset, you can ignore this email."
    )
    html = (
        f"<p>Reset your <strong>{settings.APP_NAME}</strong> password:</p>"
        f"<p><a href=\"{reset_url}\">Choose a new password</a></p>"
        f"<p>This link expires in {settings.PASSWORD_RESET_EXPIRE_HOURS} hour(s).</p>"
        f"<p style=\"color:#666;font-size:12px\">If you did not request this, ignore this message.</p>"
    )
    await send_email(to_email, subject, text, html)
