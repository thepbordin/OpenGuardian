import logging
import smtplib
from email.message import EmailMessage
from jinja2 import Environment, FileSystemLoader
from pathlib import Path

from openguardian.config.settings import settings
from openguardian.analysis.detector import AnomalyFlag

logger = logging.getLogger(__name__)

TEMPLATES_DIR = Path(__file__).parent / "templates"

class EmailNotifier:
    """
    Constructs and sends SMTP communications strictly enforcing privacy redaction templates.
    """
    def __init__(self):
        self._env = Environment(loader=FileSystemLoader(searchpath=str(TEMPLATES_DIR)))
        
    def _send_email(self, subject: str, html_content: str):
        if not settings.smtp_username or not settings.recipient_address:
            logger.warning("SMTP not fully configured. Notification skipped securely.")
            return

        msg = EmailMessage()
        msg['Subject'] = subject
        msg['From'] = settings.smtp_username
        msg['To'] = settings.recipient_address
        msg.add_alternative(html_content, subtype='html')

        try:
            with smtplib.SMTP(settings.smtp_host, settings.smtp_port) as server:
                server.starttls()
                server.login(settings.smtp_username, settings.smtp_password.get_secret_value())
                server.send_message(msg)
            logger.info(f"OpenGuardian alert dispatched successfully to {settings.recipient_address}")
        except Exception as e:
            logger.error(f"Email delivery failed: {e}")
            # F8.5 requires failure not to crash the service
            
    def send_critical_alert(self, flag: AnomalyFlag):
        """Immediately transmits a warning template based off a critical behavior deviation."""
        template = self._env.get_template("critical_alert.html")
        html = template.render(flag=flag)
        self._send_email(f"[OpenGuardian] Critical Behavior Alert: {flag.category.upper()}", html)

    def send_weekly_digest(self, flags: list[AnomalyFlag]):
        """Batches low-priority info/warnings and transmits async."""
        template = self._env.get_template("weekly_digest.html")
        html = template.render(flags=flags)
        
        # Only send digest if there are actionable items
        if flags:
            self._send_email("[OpenGuardian] Weekly Behavior Digest", html)

email_notifier = EmailNotifier()
