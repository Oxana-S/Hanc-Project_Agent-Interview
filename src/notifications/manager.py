"""
Notification Manager for Hanc.AI Voice Consultant.

Sends email notifications to the manager when an anketa is confirmed,
optionally sends session links to clients, and triggers webhook events.

All notification methods are async and designed to be fire-and-forget:
they log success/failure but never raise exceptions to the caller.
"""

import asyncio
import hashlib
import hmac
import json
import os
import smtplib
import ssl
from datetime import datetime, timezone
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path
from typing import Any, Dict, Optional

import structlog
import yaml

from html import escape as _html_escape

from src.notifications.models import NotificationConfig

logger = structlog.get_logger("notifications")

# Default config path relative to project root
DEFAULT_CONFIG_PATH = "config/notifications.yaml"

# Default YAML content written when config file does not exist
_DEFAULT_CONFIG_YAML = """\
# Notifications configuration
email:
  enabled: false
  smtp_server: "smtp.gmail.com"
  smtp_port: 587
  use_tls: true
  username: ""
  password: ""
  from_address: "noreply@hanc.ai"

  # Manager notification
  manager_email: "manager@hanc.ai"
  manager_subject: "Новая анкета от {company_name}"

  # Client notification (session link)
  client_subject: "Ваша консультация с Hanc.AI"

webhooks:
  enabled: false
  on_confirm: ""
  on_complete: ""
  secret: ""
  timeout_seconds: 10
"""


class NotificationManager:
    """Manages email and webhook notifications for consultation sessions.

    Usage::

        notifier = NotificationManager()
        await notifier.on_session_confirmed(session)
    """

    def __init__(self, config_path: str = DEFAULT_CONFIG_PATH) -> None:
        self.config_path = Path(config_path)
        self.config = self._load_config()

    # ------------------------------------------------------------------
    # Config loading
    # ------------------------------------------------------------------

    def _load_config(self) -> NotificationConfig:
        """Load notification config from YAML, creating a default file if absent."""
        if not self.config_path.exists():
            logger.info(
                "notifications_config_not_found",
                path=str(self.config_path),
                action="creating_default",
            )
            self.config_path.parent.mkdir(parents=True, exist_ok=True)
            self.config_path.write_text(_DEFAULT_CONFIG_YAML, encoding="utf-8")
            return NotificationConfig()

        try:
            raw = yaml.safe_load(self.config_path.read_text(encoding="utf-8")) or {}
            return NotificationConfig(**raw)
        except Exception as exc:
            logger.error("notifications_config_load_error", error=str(exc))
            return NotificationConfig()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def on_session_confirmed(self, session: Any) -> None:
        """Called when an anketa is confirmed.

        Triggers manager email and on_confirm webhook in parallel-safe manner.
        Errors are caught and logged; the caller is never blocked.
        """
        logger.info(
            "notification_session_confirmed",
            session_id=getattr(session, "session_id", None),
        )

        await self.send_manager_notification(session)
        await self.trigger_webhook("on_confirm", session)

    async def send_manager_notification(self, session: Any) -> None:
        """Send an email to the manager with the anketa summary."""
        email_cfg = self.config.email
        if not email_cfg.enabled:
            logger.debug("manager_email_skipped", reason="email_disabled")
            return

        try:
            company = getattr(session, "company_name", None) or "Без названия"
            subject = email_cfg.manager_subject.format(company_name=company)
            body = self._build_manager_email_body(session)

            await asyncio.to_thread(
                self._send_email,
                to_address=email_cfg.manager_email,
                subject=subject,
                body_html=body,
            )
            logger.info(
                "manager_email_sent",
                to=email_cfg.manager_email,
                session_id=getattr(session, "session_id", None),
            )
        except Exception as exc:
            logger.error(
                "manager_email_failed",
                error=str(exc),
                session_id=getattr(session, "session_id", None),
            )

    async def send_client_link(self, email: str, session: Any) -> None:
        """Send the unique session link to the client."""
        email_cfg = self.config.email
        if not email_cfg.enabled:
            logger.debug("client_email_skipped", reason="email_disabled")
            return

        try:
            unique_link = getattr(session, "unique_link", "")
            company = getattr(session, "company_name", None) or "Hanc.AI"
            subject = email_cfg.client_subject

            body = self._build_client_email_body(session, unique_link)

            await asyncio.to_thread(
                self._send_email,
                to_address=email,
                subject=subject,
                body_html=body,
            )
            logger.info(
                "client_email_sent",
                to=email,
                session_id=getattr(session, "session_id", None),
            )
        except Exception as exc:
            logger.error(
                "client_email_failed",
                error=str(exc),
                session_id=getattr(session, "session_id", None),
            )

    async def trigger_webhook(self, event_type: str, session: Any) -> None:
        """POST session data to the configured webhook URL.

        Includes ``X-Webhook-Signature`` header (HMAC-SHA256 of body).
        """
        wh_cfg = self.config.webhooks
        if not wh_cfg.enabled:
            logger.debug("webhook_skipped", reason="webhooks_disabled")
            return

        url = getattr(wh_cfg, event_type, "")
        if not url:
            logger.debug("webhook_skipped", reason="no_url", event_type=event_type)
            return

        try:
            import aiohttp

            payload = self._build_webhook_payload(event_type, session)
            body_bytes = json.dumps(payload, ensure_ascii=False, default=str).encode("utf-8")

            headers: Dict[str, str] = {"Content-Type": "application/json"}

            if wh_cfg.secret:
                signature = hmac.new(
                    wh_cfg.secret.encode("utf-8"),
                    body_bytes,
                    hashlib.sha256,
                ).hexdigest()
                headers["X-Webhook-Signature"] = signature

            timeout = aiohttp.ClientTimeout(total=wh_cfg.timeout_seconds)

            async with aiohttp.ClientSession(timeout=timeout) as http:
                async with http.post(url, data=body_bytes, headers=headers) as resp:
                    logger.info(
                        "webhook_triggered",
                        event_type=event_type,
                        url=url,
                        status=resp.status,
                        session_id=getattr(session, "session_id", None),
                    )
        except ImportError:
            logger.warning(
                "webhook_aiohttp_missing",
                detail="Install aiohttp to enable webhook support: pip install aiohttp",
            )
        except Exception as exc:
            logger.error(
                "webhook_failed",
                event_type=event_type,
                url=url,
                error=str(exc),
                session_id=getattr(session, "session_id", None),
            )

    # ------------------------------------------------------------------
    # Email helpers
    # ------------------------------------------------------------------

    def _send_email(self, to_address: str, subject: str, body_html: str) -> None:
        """Send an email via SMTP (synchronous, called from async context)."""
        email_cfg = self.config.email

        msg = MIMEMultipart("alternative")
        msg["From"] = email_cfg.from_address
        msg["To"] = to_address
        msg["Subject"] = subject
        msg.attach(MIMEText(body_html, "html", "utf-8"))

        if email_cfg.use_tls:
            context = ssl.create_default_context()
            with smtplib.SMTP(email_cfg.smtp_server, email_cfg.smtp_port, timeout=30) as server:
                server.starttls(context=context)
                if email_cfg.username and email_cfg.password:
                    server.login(email_cfg.username, email_cfg.password)
                server.sendmail(email_cfg.from_address, to_address, msg.as_string())
        else:
            with smtplib.SMTP(email_cfg.smtp_server, email_cfg.smtp_port, timeout=30) as server:
                if email_cfg.username and email_cfg.password:
                    server.login(email_cfg.username, email_cfg.password)
                server.sendmail(email_cfg.from_address, to_address, msg.as_string())

    def _build_manager_email_body(self, session: Any) -> str:
        """Build an HTML email body with the anketa summary for the manager."""
        # R6-04: Escape all user-provided data to prevent HTML injection
        session_id = _html_escape(str(getattr(session, "session_id", "N/A")))
        company = _html_escape(getattr(session, "company_name", None) or "Без названия")
        contact = _html_escape(getattr(session, "contact_name", None) or "Не указано")
        created = getattr(session, "created_at", None)
        created_str = created.strftime("%d.%m.%Y %H:%M") if isinstance(created, datetime) else "N/A"
        duration = getattr(session, "duration_seconds", 0)
        duration_min = round(duration / 60, 1) if duration else 0

        # Anketa markdown or fallback
        anketa_md = _html_escape(getattr(session, "anketa_md", None) or "")
        anketa_data = getattr(session, "anketa_data", None)

        # Build a structured text summary from anketa_data if available
        data_summary = ""
        if anketa_data and isinstance(anketa_data, dict):
            lines = []
            for key, value in anketa_data.items():
                if value is not None and value != "" and value != []:
                    lines.append(f"<tr><td style='padding:4px 8px;font-weight:bold;'>{_html_escape(str(key))}</td>"
                                 f"<td style='padding:4px 8px;'>{_html_escape(str(value))}</td></tr>")
            if lines:
                data_summary = (
                    "<table border='1' cellpadding='0' cellspacing='0' "
                    "style='border-collapse:collapse;margin-top:12px;'>"
                    + "".join(lines)
                    + "</table>"
                )

        html = f"""\
<html>
<body style="font-family: Arial, sans-serif; color: #333;">
<h2>Новая подтверждённая анкета</h2>
<table style="margin-bottom:16px;">
  <tr><td><b>ID сессии:</b></td><td>{session_id}</td></tr>
  <tr><td><b>Компания:</b></td><td>{company}</td></tr>
  <tr><td><b>Контакт:</b></td><td>{contact}</td></tr>
  <tr><td><b>Дата создания:</b></td><td>{created_str}</td></tr>
  <tr><td><b>Длительность:</b></td><td>{duration_min} мин</td></tr>
</table>

<h3>Данные анкеты</h3>
{data_summary if data_summary else "<p><em>Нет структурированных данных</em></p>"}

{f"<h3>Анкета (Markdown)</h3><pre>{anketa_md}</pre>" if anketa_md else ""}

<hr>
<p style="font-size:12px;color:#999;">Hanc.AI Voice Consultant</p>
</body>
</html>"""
        return html

    def _build_client_email_body(self, session: Any, unique_link: str) -> str:
        """Build an HTML email body with the session link for the client."""
        company = _html_escape(getattr(session, "company_name", None) or "Hanc.AI")
        unique_link = _html_escape(unique_link)
        base_url = os.getenv("PUBLIC_URL", "https://app.hanc.ai").rstrip("/")

        html = f"""\
<html>
<body style="font-family: Arial, sans-serif; color: #333;">
<h2>Ваша консультация с {company}</h2>
<p>Спасибо за прохождение консультации!</p>
<p>Вы можете вернуться к вашей сессии в любое время по этой ссылке:</p>
<p style="margin:16px 0;">
  <a href="{base_url}/session/{unique_link}"
     style="background:#2563eb;color:#fff;padding:10px 24px;
            text-decoration:none;border-radius:6px;font-size:16px;">
    Открыть сессию
  </a>
</p>
<p style="font-size:13px;color:#666;">
  Если кнопка не работает, скопируйте ссылку:
  {base_url}/session/{unique_link}
</p>
<hr>
<p style="font-size:12px;color:#999;">Hanc.AI Voice Consultant</p>
</body>
</html>"""
        return html

    # ------------------------------------------------------------------
    # Webhook helpers
    # ------------------------------------------------------------------

    def _build_webhook_payload(self, event_type: str, session: Any) -> Dict[str, Any]:
        """Build the JSON payload for a webhook event.

        R18-07: Only include essential fields (not full dialogue/voice_config).
        """
        # R18-07: Whitelist essential fields instead of dumping entire session
        _WEBHOOK_FIELDS = {
            "session_id", "status", "company_name", "session_type",
            "anketa_data", "anketa_md", "created_at", "duration_seconds",
            "contact_name", "contact_email", "contact_phone",
        }
        session_dict: Dict[str, Any] = {}
        if hasattr(session, "model_dump"):
            full = session.model_dump()
            session_dict = {k: v for k, v in full.items() if k in _WEBHOOK_FIELDS}
        elif hasattr(session, "dict"):
            full = session.dict()
            session_dict = {k: v for k, v in full.items() if k in _WEBHOOK_FIELDS}
        else:
            session_dict = {
                "session_id": getattr(session, "session_id", None),
                "status": getattr(session, "status", None),
                "company_name": getattr(session, "company_name", None),
            }

        return {
            "event": event_type,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "session": session_dict,
        }
