"""
Pydantic models for notification configuration.

Defines the schema for email (SMTP) and webhook settings
loaded from config/notifications.yaml.
"""

from typing import Optional

from pydantic import BaseModel, Field


class EmailConfig(BaseModel):
    """SMTP email configuration."""

    enabled: bool = Field(default=False, description="Whether email notifications are enabled")
    smtp_server: str = Field(default="smtp.gmail.com", description="SMTP server hostname")
    smtp_port: int = Field(default=587, description="SMTP server port")
    use_tls: bool = Field(default=True, description="Use STARTTLS for SMTP connection")
    username: str = Field(default="", description="SMTP authentication username")
    password: str = Field(default="", description="SMTP authentication password")
    from_address: str = Field(default="noreply@hanc.ai", description="Sender email address")

    # Manager notification
    manager_email: str = Field(default="manager@hanc.ai", description="Manager email for anketa notifications")
    manager_subject: str = Field(
        default="Новая анкета от {company_name}",
        description="Email subject template for manager notifications",
    )

    # Client notification
    client_subject: str = Field(
        default="Ваша консультация с Hanc.AI",
        description="Email subject for client session link",
    )


class WebhookConfig(BaseModel):
    """Webhook configuration."""

    enabled: bool = Field(default=False, description="Whether webhooks are enabled")
    on_confirm: str = Field(default="", description="URL to POST when anketa is confirmed")
    on_complete: str = Field(default="", description="URL to POST when session ends")
    secret: str = Field(default="", description="HMAC-SHA256 secret for webhook signature")
    timeout_seconds: int = Field(default=10, description="HTTP request timeout in seconds")


class NotificationConfig(BaseModel):
    """Top-level notification configuration combining email and webhooks."""

    email: EmailConfig = Field(default_factory=EmailConfig)
    webhooks: WebhookConfig = Field(default_factory=WebhookConfig)
