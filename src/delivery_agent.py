"""Delivery Agent — sends newsletter via Telegram and Email."""

from __future__ import annotations

import asyncio
import os
import smtplib
import traceback
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path

import aiohttp
import markdown
import yaml

from src.utils.logger import get_logger
from src.utils.paths import resolve_path
from src.utils.timezone_utils import local_date_str

logger = get_logger(__name__)

TELEGRAM_MAX_LENGTH = int(os.getenv("TELEGRAM_MAX_MESSAGE_LENGTH", "4000"))


class DeliveryAgent:
    """Deliver newsletter to Telegram channel and email recipients."""

    def __init__(
        self,
        delivery_config: str | Path = "config/delivery_config.yaml",
    ) -> None:
        self.delivery_config_path = resolve_path(delivery_config)
        self._config: dict | None = None

        self.telegram_token = os.getenv("TELEGRAM_BOT_TOKEN", "")
        self.telegram_channel = os.getenv("TELEGRAM_CHANNEL_ID", "")
        self.smtp_server = os.getenv(
            "SMTP_SERVER",
            os.getenv("EMAIL_SMTP_SERVER", "smtp.gmail.com"),
        )
        self.smtp_port = int(
            os.getenv("SMTP_PORT", os.getenv("EMAIL_SMTP_PORT", "587"))
        )
        self.smtp_username = os.getenv(
            "SMTP_USERNAME",
            os.getenv("EMAIL_USERNAME", ""),
        )
        self.smtp_password = os.getenv(
            "SMTP_PASSWORD",
            os.getenv("EMAIL_PASSWORD", ""),
        ).replace(" ", "")
        self.smtp_from = os.getenv("SMTP_FROM", self.smtp_username)
        self.email_recipients = [
            r.strip()
            for r in os.getenv("EMAIL_RECIPIENTS", "").split(",")
            if r.strip()
        ]

        logger.info(
            "delivery.init",
            config_path=str(self.delivery_config_path),
            smtp_server=self.smtp_server,
            smtp_port=self.smtp_port,
            smtp_username=self.smtp_username or "(not set)",
            smtp_from=self.smtp_from or "(not set)",
            recipient_count=len(self.email_recipients),
            telegram_configured=bool(self.telegram_token and self.telegram_channel),
        )

    @property
    def config(self) -> dict:
        if self._config is None:
            logger.debug("delivery.load_config", path=str(self.delivery_config_path))
            with self.delivery_config_path.open(encoding="utf-8") as f:
                self._config = yaml.safe_load(f)
        return self._config

    def _split_message(self, text: str, max_length: int = TELEGRAM_MAX_LENGTH) -> list[str]:
        if len(text) <= max_length:
            return [text]

        chunks: list[str] = []
        current = ""
        for paragraph in text.split("\n\n"):
            if len(current) + len(paragraph) + 2 <= max_length:
                current = f"{current}\n\n{paragraph}" if current else paragraph
            else:
                if current:
                    chunks.append(current)
                if len(paragraph) > max_length:
                    for i in range(0, len(paragraph), max_length):
                        chunks.append(paragraph[i : i + max_length])
                    current = ""
                else:
                    current = paragraph
        if current:
            chunks.append(current)
        return chunks

    async def send_telegram(self, newsletter: str) -> bool:
        if not self.config.get("telegram", {}).get("enabled", True):
            logger.info("delivery.telegram_skipped", reason="disabled_in_config")
            return True

        if not self.telegram_token or not self.telegram_channel:
            logger.warning(
                "delivery.telegram_skipped",
                reason="missing_credentials",
                has_token=bool(self.telegram_token),
                has_channel=bool(self.telegram_channel),
            )
            return False

        max_len = self.config.get("telegram", {}).get("max_message_length", TELEGRAM_MAX_LENGTH)
        chunks = self._split_message(newsletter, max_len)
        url = f"https://api.telegram.org/bot{self.telegram_token}/sendMessage"

        logger.info(
            "delivery.telegram_sending",
            channel=self.telegram_channel,
            chunks=len(chunks),
            newsletter_chars=len(newsletter),
        )

        try:
            async with aiohttp.ClientSession() as session:
                for i, chunk in enumerate(chunks):
                    payload = {
                        "chat_id": self.telegram_channel,
                        "text": chunk,
                        "parse_mode": "Markdown",
                        "disable_web_page_preview": True,
                    }
                    async with session.post(url, json=payload) as resp:
                        body = await resp.text()
                        if resp.status != 200:
                            logger.error(
                                "delivery.telegram_chunk_failed",
                                chunk=i,
                                status=resp.status,
                                response_body=body,
                            )
                            return False
                        logger.debug(
                            "delivery.telegram_chunk_ok",
                            chunk=i,
                            status=resp.status,
                            response_preview=body[:300],
                        )
            logger.info("delivery.telegram_sent", chunks=len(chunks))
            return True
        except Exception as e:
            logger.exception(
                "delivery.telegram_failed",
                error=str(e),
                traceback=traceback.format_exc(),
            )
            return False

    def _email_missing_fields(self) -> list[str]:
        missing: list[str] = []
        if not self.smtp_username:
            missing.append("SMTP_USERNAME")
        if not self.smtp_password:
            missing.append("SMTP_PASSWORD")
        if not self.email_recipients:
            missing.append("EMAIL_RECIPIENTS")
        if not self.smtp_server:
            missing.append("SMTP_SERVER")
        return missing

    def _send_email_sync(self, msg: MIMEMultipart) -> None:
        with smtplib.SMTP(self.smtp_server, self.smtp_port, timeout=30) as server:
            server.starttls()
            server.login(self.smtp_username, self.smtp_password)
            server.sendmail(
                self.smtp_from,
                self.email_recipients,
                msg.as_string(),
            )

    async def send_email(self, newsletter: str, subject: str | None = None) -> bool:
        if not self.config.get("email", {}).get("enabled", True):
            logger.info("delivery.email_skipped", reason="disabled_in_config")
            return True

        missing = self._email_missing_fields()
        if missing:
            logger.warning(
                "delivery.email_skipped",
                reason="missing_credentials",
                missing_fields=missing,
            )
            return False

        prefix = self.config.get("email", {}).get("subject_prefix", "AI News Digest")
        subject = subject or f"{prefix} - {local_date_str()}"

        html_body = markdown.markdown(newsletter, extensions=["tables", "fenced_code"])

        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = self.smtp_from
        msg["To"] = ", ".join(self.email_recipients)
        msg.attach(MIMEText(newsletter, "plain", "utf-8"))
        msg.attach(MIMEText(html_body, "html", "utf-8"))

        logger.info(
            "delivery.email_sending",
            smtp_server=self.smtp_server,
            smtp_port=self.smtp_port,
            smtp_username=self.smtp_username,
            smtp_from=self.smtp_from,
            recipients=self.email_recipients,
            subject=subject,
            body_chars=len(newsletter),
        )

        try:
            try:
                import aiosmtplib

                response = await aiosmtplib.send(
                    msg,
                    sender=self.smtp_from,
                    recipients=self.email_recipients,
                    hostname=self.smtp_server,
                    port=self.smtp_port,
                    username=self.smtp_username,
                    password=self.smtp_password,
                    start_tls=True,
                )
                logger.info(
                    "delivery.email_sent",
                    transport="aiosmtplib",
                    recipients=self.email_recipients,
                    smtp_response=str(response),
                )
            except ImportError:
                logger.warning(
                    "delivery.aiosmtplib_missing",
                    fallback="smtplib",
                )
                await asyncio.to_thread(self._send_email_sync, msg)
                logger.info(
                    "delivery.email_sent",
                    transport="smtplib",
                    recipients=self.email_recipients,
                )
            return True
        except Exception as e:
            logger.exception(
                "delivery.email_failed",
                error=str(e),
                smtp_server=self.smtp_server,
                smtp_port=self.smtp_port,
                traceback=traceback.format_exc(),
            )
            return False

    async def deliver(self, newsletter: str) -> dict[str, bool]:
        logger.info("delivery.start", newsletter_chars=len(newsletter))
        telegram_ok = await self.send_telegram(newsletter)
        email_ok = await self.send_email(newsletter)

        status = {"telegram": telegram_ok, "email": email_ok}
        logger.info("delivery.complete", status=status)
        return status

    async def deliver_newsletter(self, newsletter: str) -> dict[str, bool | str | None]:
        """Save and deliver newsletter via Telegram and email (orchestrator entry point)."""
        content = (newsletter or "").strip()
        if not content:
            logger.warning("delivery.skipped", reason="empty_newsletter")
            return {
                "telegram": False,
                "email": False,
                "newsletter_path": None,
                "html_path": None,
            }

        saved_path = self.save_newsletter(content)
        logger.info("delivery.newsletter_ready", path=str(saved_path), bytes=len(content))
        status = await self.deliver(content)
        return {
            "telegram": status.get("telegram", False),
            "email": status.get("email", False),
            "newsletter_path": str(saved_path),
            "html_path": str(saved_path.with_suffix(".html")),
        }

    def save_newsletter(self, newsletter: str, output_dir: str | None = None) -> Path:
        configured_dir = self.config.get("newsletter", {}).get(
            "output_dir", "outputs/newsletters"
        )
        out_dir = resolve_path(output_dir or configured_dir)
        out_dir.mkdir(parents=True, exist_ok=True)

        date_str = local_date_str()
        filename = self.config.get("newsletter", {}).get(
            "filename_format", "{date}_newsletter.md"
        ).format(date=date_str)

        filepath = out_dir / filename
        filepath.write_text(newsletter, encoding="utf-8")

        html_path = filepath.with_suffix(".html")
        html_path.write_text(
            markdown.markdown(newsletter, extensions=["tables", "fenced_code"]),
            encoding="utf-8",
        )

        logger.info(
            "delivery.newsletter_saved",
            markdown_path=str(filepath),
            html_path=str(html_path),
            bytes=len(newsletter),
        )
        return filepath
