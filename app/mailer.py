"""Sends account emails. Addresses and links are never logged."""

import json
import logging
import smtplib
import ssl
from dataclasses import dataclass
from email.message import EmailMessage
from pathlib import Path
from typing import Protocol

from app.config import Settings

log = logging.getLogger("tally.mail")


class Mailer(Protocol):
    def send(self, to: str, subject: str, body: str) -> None: ...


@dataclass
class SmtpMailer:
    host: str
    port: int
    username: str
    password: str
    sender: str

    def send(self, to: str, subject: str, body: str) -> None:
        message = EmailMessage()
        message["From"] = self.sender
        message["To"] = to
        message["Subject"] = subject
        message.set_content(body)
        with smtplib.SMTP(self.host, self.port, timeout=20) as smtp:
            smtp.starttls(context=ssl.create_default_context())
            smtp.login(self.username, self.password)
            smtp.send_message(message)


@dataclass
class OutboxMailer:
    """Writes to a local file, for development and tests. Nothing leaves the machine."""

    path: Path

    def send(self, to: str, subject: str, body: str) -> None:
        with self.path.open("a") as outbox:
            outbox.write(json.dumps({"to": to, "subject": subject, "body": body}) + "\n")


def build_mailer(settings: Settings) -> Mailer | None:
    if not settings.email_pepper or not settings.public_url:
        return None
    if settings.email_outbox:
        return OutboxMailer(settings.email_outbox)
    if settings.smtp_host and settings.email_from:
        return SmtpMailer(
            settings.smtp_host,
            settings.smtp_port,
            settings.smtp_user,
            settings.smtp_password,
            settings.email_from,
        )
    return None


def send_quietly(mailer: Mailer, to: str, subject: str, body: str) -> None:
    """Runs after the response, so its timing and errors can't reveal who has an account."""
    try:
        mailer.send(to, subject, body)
    except Exception as exc:  # noqa: BLE001 - a mail failure must not surface to the requester
        log.error("Email send failed: %s", type(exc).__name__)
