"""
Unit tests for notification models and NotificationManager.
"""

import hashlib
import hmac
import json
import sys
import os
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import yaml

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from src.notifications.models import EmailConfig, WebhookConfig, NotificationConfig
from src.notifications.manager import NotificationManager


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_session(**overrides):
    """Create a simple session-like object with sensible defaults."""
    defaults = {
        "session_id": "sess-001",
        "company_name": "TestCorp",
        "contact_name": "Ivan Petrov",
        "created_at": datetime(2026, 1, 15, 10, 30, 0),
        "duration_seconds": 900,
        "unique_link": "abc-def-123",
        "anketa_data": {"industry": "IT", "employees": 50},
        "anketa_md": "## Anketa\n- Industry: IT",
        "status": "confirmed",
    }
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


def _write_yaml_config(path, email_overrides=None, webhook_overrides=None):
    """Write a notifications YAML config to *path*."""
    email = {
        "enabled": False,
        "smtp_server": "smtp.example.com",
        "smtp_port": 587,
        "use_tls": True,
        "username": "user",
        "password": "pass",
        "from_address": "no-reply@example.com",
        "manager_email": "mgr@example.com",
        "manager_subject": "New anketa from {company_name}",
        "client_subject": "Your consultation",
    }
    webhooks = {
        "enabled": False,
        "on_confirm": "",
        "on_complete": "",
        "secret": "",
        "timeout_seconds": 10,
    }
    if email_overrides:
        email.update(email_overrides)
    if webhook_overrides:
        webhooks.update(webhook_overrides)

    data = {"email": email, "webhooks": webhooks}
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.dump(data, allow_unicode=True), encoding="utf-8")
    return data


# ===================================================================
# Model default tests
# ===================================================================

class TestNotificationConfigDefaults:
    """Test that NotificationConfig and sub-models have correct defaults."""

    def test_notification_config_email_disabled_by_default(self):
        cfg = NotificationConfig()
        assert cfg.email.enabled is False

    def test_notification_config_webhooks_disabled_by_default(self):
        cfg = NotificationConfig()
        assert cfg.webhooks.enabled is False


class TestEmailConfigDefaults:
    """Test EmailConfig defaults."""

    def test_enabled_default(self):
        cfg = EmailConfig()
        assert cfg.enabled is False

    def test_smtp_server_default(self):
        cfg = EmailConfig()
        assert cfg.smtp_server == "smtp.gmail.com"

    def test_smtp_port_default(self):
        cfg = EmailConfig()
        assert cfg.smtp_port == 587

    def test_use_tls_default(self):
        cfg = EmailConfig()
        assert cfg.use_tls is True

    def test_username_default(self):
        cfg = EmailConfig()
        assert cfg.username == ""

    def test_password_default(self):
        cfg = EmailConfig()
        assert cfg.password == ""

    def test_from_address_default(self):
        cfg = EmailConfig()
        assert cfg.from_address == "noreply@hanc.ai"

    def test_manager_email_default(self):
        cfg = EmailConfig()
        assert cfg.manager_email == "manager@hanc.ai"

    def test_manager_subject_default(self):
        cfg = EmailConfig()
        assert "{company_name}" in cfg.manager_subject

    def test_client_subject_default(self):
        cfg = EmailConfig()
        assert cfg.client_subject == "Ваша консультация с Hanc.AI"


class TestWebhookConfigDefaults:
    """Test WebhookConfig defaults."""

    def test_enabled_default(self):
        cfg = WebhookConfig()
        assert cfg.enabled is False

    def test_on_confirm_default(self):
        cfg = WebhookConfig()
        assert cfg.on_confirm == ""

    def test_on_complete_default(self):
        cfg = WebhookConfig()
        assert cfg.on_complete == ""

    def test_secret_default(self):
        cfg = WebhookConfig()
        assert cfg.secret == ""

    def test_timeout_seconds_default(self):
        cfg = WebhookConfig()
        assert cfg.timeout_seconds == 10


# ===================================================================
# NotificationManager config loading
# ===================================================================

class TestNotificationManagerConfigLoading:
    """Test config loading from YAML and default creation."""

    def test_loads_config_from_yaml(self, tmp_path):
        """Manager should parse values written to a YAML file."""
        cfg_file = tmp_path / "notifications.yaml"
        _write_yaml_config(
            cfg_file,
            email_overrides={"enabled": True, "manager_email": "boss@test.com"},
            webhook_overrides={"enabled": True, "on_confirm": "https://hook.example.com/confirm"},
        )

        mgr = NotificationManager(config_path=str(cfg_file))

        assert mgr.config.email.enabled is True
        assert mgr.config.email.manager_email == "boss@test.com"
        assert mgr.config.webhooks.enabled is True
        assert mgr.config.webhooks.on_confirm == "https://hook.example.com/confirm"

    def test_creates_default_config_when_missing(self, tmp_path):
        """When the config file does not exist, the manager should create it and use defaults."""
        cfg_file = tmp_path / "subdir" / "notifications.yaml"
        assert not cfg_file.exists()

        mgr = NotificationManager(config_path=str(cfg_file))

        # File must have been created
        assert cfg_file.exists()
        # Config should be defaults
        assert mgr.config.email.enabled is False
        assert mgr.config.webhooks.enabled is False


# ===================================================================
# send_manager_notification
# ===================================================================

class TestSendManagerNotification:
    """Test send_manager_notification behaviour."""

    @pytest.mark.asyncio
    async def test_skips_when_email_disabled(self, tmp_path):
        """No email should be sent when email is disabled."""
        cfg_file = tmp_path / "notifications.yaml"
        _write_yaml_config(cfg_file, email_overrides={"enabled": False})
        mgr = NotificationManager(config_path=str(cfg_file))

        with patch.object(mgr, "_send_email") as mock_send:
            await mgr.send_manager_notification(_make_session())
            mock_send.assert_not_called()

    @pytest.mark.asyncio
    async def test_calls_send_email_when_enabled(self, tmp_path):
        """_send_email should be called with the correct arguments when enabled."""
        cfg_file = tmp_path / "notifications.yaml"
        _write_yaml_config(cfg_file, email_overrides={"enabled": True})
        mgr = NotificationManager(config_path=str(cfg_file))

        with patch.object(mgr, "_send_email") as mock_send:
            session = _make_session(company_name="Acme")
            await mgr.send_manager_notification(session)

            mock_send.assert_called_once()
            call_kwargs = mock_send.call_args
            # to_address should be the manager_email from config
            assert call_kwargs[1]["to_address"] == "mgr@example.com" or call_kwargs[0][0] == "mgr@example.com"


# ===================================================================
# trigger_webhook
# ===================================================================

class TestTriggerWebhook:
    """Test trigger_webhook behaviour."""

    @pytest.mark.asyncio
    async def test_skips_when_webhooks_disabled(self, tmp_path):
        """No HTTP call should happen when webhooks are disabled."""
        cfg_file = tmp_path / "notifications.yaml"
        _write_yaml_config(cfg_file, webhook_overrides={"enabled": False})
        mgr = NotificationManager(config_path=str(cfg_file))

        with patch("src.notifications.manager.json") as mock_json:
            await mgr.trigger_webhook("on_confirm", _make_session())
            # json.dumps should never be called because we bail out early
            mock_json.dumps.assert_not_called()

    @pytest.mark.asyncio
    async def test_hmac_signature_is_correct(self, tmp_path):
        """The HMAC-SHA256 signature sent in the header must match a local computation."""
        secret = "my-webhook-secret"
        cfg_file = tmp_path / "notifications.yaml"
        _write_yaml_config(
            cfg_file,
            webhook_overrides={
                "enabled": True,
                "on_confirm": "https://hook.example.com/confirm",
                "secret": secret,
                "timeout_seconds": 5,
            },
        )
        mgr = NotificationManager(config_path=str(cfg_file))
        session = _make_session()

        # Freeze datetime.now(timezone.utc) so the timestamp in the payload is deterministic
        from datetime import timezone
        frozen_now = datetime(2026, 2, 1, 12, 0, 0, tzinfo=timezone.utc)

        with patch("src.notifications.manager.datetime") as mock_dt:
            mock_dt.now.return_value = frozen_now
            # Keep isinstance checks working for _build_manager_email_body
            mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)

            payload = mgr._build_webhook_payload("on_confirm", session)

        body_bytes = json.dumps(payload, ensure_ascii=False, default=str).encode("utf-8")
        expected_sig = hmac.new(
            secret.encode("utf-8"), body_bytes, hashlib.sha256
        ).hexdigest()

        # Capture what aiohttp receives
        captured_headers = {}

        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.__aenter__ = AsyncMock(return_value=mock_response)
        mock_response.__aexit__ = AsyncMock(return_value=False)

        mock_session_ctx = MagicMock()

        def capture_post(url, data=None, headers=None):
            captured_headers.update(headers or {})
            return mock_response

        mock_session_ctx.post = capture_post

        mock_client_session = MagicMock()
        mock_client_session.__aenter__ = AsyncMock(return_value=mock_session_ctx)
        mock_client_session.__aexit__ = AsyncMock(return_value=False)

        # aiohttp is imported locally inside trigger_webhook, so we patch
        # it in sys.modules rather than as a module-level attribute.
        mock_aiohttp = MagicMock()
        mock_aiohttp.ClientTimeout = MagicMock()
        mock_aiohttp.ClientSession = MagicMock(return_value=mock_client_session)

        with patch.dict("sys.modules", {"aiohttp": mock_aiohttp}):
            with patch("src.notifications.manager.datetime") as mock_dt2:
                mock_dt2.now.return_value = frozen_now
                mock_dt2.side_effect = lambda *a, **kw: datetime(*a, **kw)
                await mgr.trigger_webhook("on_confirm", session)

        assert "X-Webhook-Signature" in captured_headers
        assert captured_headers["X-Webhook-Signature"] == expected_sig


# ===================================================================
# Email body builders
# ===================================================================

class TestBuildManagerEmailBody:
    """Test _build_manager_email_body HTML content."""

    def test_contains_session_fields(self, tmp_path):
        cfg_file = tmp_path / "notifications.yaml"
        _write_yaml_config(cfg_file)
        mgr = NotificationManager(config_path=str(cfg_file))

        session = _make_session(
            session_id="sess-xyz",
            company_name="MegaCorp",
            contact_name="Anna Smirnova",
        )
        html = mgr._build_manager_email_body(session)

        assert "sess-xyz" in html
        assert "MegaCorp" in html
        assert "Anna Smirnova" in html
        # Duration: 900 s -> 15.0 min
        assert "15.0" in html

    def test_contains_anketa_data_keys(self, tmp_path):
        cfg_file = tmp_path / "notifications.yaml"
        _write_yaml_config(cfg_file)
        mgr = NotificationManager(config_path=str(cfg_file))

        session = _make_session(anketa_data={"industry": "Finance", "staff_count": 200})
        html = mgr._build_manager_email_body(session)

        assert "industry" in html
        assert "Finance" in html
        assert "staff_count" in html
        assert "200" in html

    def test_contains_anketa_md(self, tmp_path):
        cfg_file = tmp_path / "notifications.yaml"
        _write_yaml_config(cfg_file)
        mgr = NotificationManager(config_path=str(cfg_file))

        session = _make_session(anketa_md="## Summary\n- item 1")
        html = mgr._build_manager_email_body(session)

        assert "## Summary" in html
        assert "item 1" in html


class TestBuildClientEmailBody:
    """Test _build_client_email_body HTML content."""

    def test_contains_unique_link(self, tmp_path):
        cfg_file = tmp_path / "notifications.yaml"
        _write_yaml_config(cfg_file)
        mgr = NotificationManager(config_path=str(cfg_file))

        session = _make_session()
        unique_link = "unique-link-456"
        html = mgr._build_client_email_body(session, unique_link)

        assert "unique-link-456" in html

    def test_contains_company_name(self, tmp_path):
        cfg_file = tmp_path / "notifications.yaml"
        _write_yaml_config(cfg_file)
        mgr = NotificationManager(config_path=str(cfg_file))

        session = _make_session(company_name="BrightFuture")
        html = mgr._build_client_email_body(session, "link-789")

        assert "BrightFuture" in html


# ===================================================================
# Webhook payload builder
# ===================================================================

class TestBuildWebhookPayload:
    """Test _build_webhook_payload structure."""

    def test_returns_correct_structure(self, tmp_path):
        cfg_file = tmp_path / "notifications.yaml"
        _write_yaml_config(cfg_file)
        mgr = NotificationManager(config_path=str(cfg_file))

        session = _make_session()
        payload = mgr._build_webhook_payload("on_confirm", session)

        assert "event" in payload
        assert payload["event"] == "on_confirm"
        assert "timestamp" in payload
        assert "session" in payload

    def test_session_contains_expected_keys(self, tmp_path):
        cfg_file = tmp_path / "notifications.yaml"
        _write_yaml_config(cfg_file)
        mgr = NotificationManager(config_path=str(cfg_file))

        session = _make_session(session_id="s-100", company_name="PayloadCorp", status="completed")
        payload = mgr._build_webhook_payload("on_complete", session)

        session_data = payload["session"]
        assert session_data["session_id"] == "s-100"
        assert session_data["company_name"] == "PayloadCorp"
        assert session_data["status"] == "completed"

    def test_timestamp_is_iso_format(self, tmp_path):
        cfg_file = tmp_path / "notifications.yaml"
        _write_yaml_config(cfg_file)
        mgr = NotificationManager(config_path=str(cfg_file))

        payload = mgr._build_webhook_payload("on_confirm", _make_session())
        # Should parse without error
        datetime.fromisoformat(payload["timestamp"])


# ===================================================================
# on_session_confirmed orchestration
# ===================================================================

class TestOnSessionConfirmed:
    """Test that on_session_confirmed calls both notification paths."""

    @pytest.mark.asyncio
    async def test_calls_send_manager_notification_and_trigger_webhook(self, tmp_path):
        cfg_file = tmp_path / "notifications.yaml"
        _write_yaml_config(cfg_file)
        mgr = NotificationManager(config_path=str(cfg_file))

        with patch.object(
            mgr, "send_manager_notification", new_callable=AsyncMock
        ) as mock_email, patch.object(
            mgr, "trigger_webhook", new_callable=AsyncMock
        ) as mock_webhook:
            session = _make_session()
            await mgr.on_session_confirmed(session)

            mock_email.assert_awaited_once_with(session)
            mock_webhook.assert_awaited_once_with("on_confirm", session)
