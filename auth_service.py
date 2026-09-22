import os
import re
import secrets
import smtplib
import time
import threading
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Tuple, Optional, Dict
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

# Regex for standard email validation
EMAIL_REGEX = re.compile(r"^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$")

class EmailAuthManager:
    """
    Manages generation, delivery, and verification of One-Time Passwords (OTPs)
    using Google SMTP (smtp.gmail.com) with graceful fallback for development.
    """
    def __init__(self):
        self._lock = threading.Lock()
        self._otp_store: Dict[str, dict] = {}
        self._last_sent: Dict[str, float] = {}

    @property
    def smtp_host(self) -> str:
        return os.getenv("SMTP_HOST", "smtp.gmail.com").strip()

    @property
    def smtp_port(self) -> int:
        try:
            return int(os.getenv("SMTP_PORT", "587"))
        except ValueError:
            return 587

    @property
    def smtp_user(self) -> str:
        return os.getenv("SMTP_USER", "").strip()

    @property
    def smtp_password(self) -> str:
        # Google App Passwords might have spaces (e.g., 'abcd efgh ijkl mnop')
        return os.getenv("SMTP_PASSWORD", "").replace(" ", "").strip()

    @property
    def sender_name(self) -> str:
        return os.getenv("SMTP_SENDER_NAME", "Multi-Agent Orchestrator").strip()

    @property
    def otp_expiry_seconds(self) -> int:
        try:
            minutes = int(os.getenv("OTP_EXPIRY_MINUTES", "10"))
            return max(60, minutes * 60)
        except ValueError:
            return 600

    @property
    def max_attempts(self) -> int:
        try:
            return int(os.getenv("OTP_MAX_ATTEMPTS", "5"))
        except ValueError:
            return 5

    def is_smtp_configured(self) -> bool:
        """Returns True if Google SMTP credentials are configured in environment."""
        return bool(self.smtp_user and self.smtp_password)

    def is_valid_email(self, email: str) -> bool:
        """Validates email format."""
        if not email or not isinstance(email, str):
            return False
        return bool(EMAIL_REGEX.match(email.strip()))

    def _generate_otp(self) -> str:
        """Generates a secure 6-digit numeric OTP."""
        return f"{secrets.randbelow(900000) + 100000}"

    def _create_email_message(self, to_email: str, otp_code: str) -> MIMEMultipart:
        """Creates a stylish multipart HTML & plain-text verification email."""
        msg = MIMEMultipart("alternative")
        msg["Subject"] = f"🔐 Your Login Code: {otp_code} - Multi-Agent Orchestrator"
        msg["From"] = f'"{self.sender_name}" <{self.smtp_user}>'
        msg["To"] = to_email

        expiry_mins = max(1, self.otp_expiry_seconds // 60)

        # Plain text fallback
        text_content = f"""Hello,

Your single-use login code for Multi-Agent Orchestrator is: {otp_code}

This code expires in {expiry_mins} minutes.
If you did not request this code, you can safely ignore this email.

Best regards,
Multi-Agent Orchestrator Team
"""

        # Modern Dark-themed HTML template
        html_content = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <title>Login Verification Code</title>
</head>
<body style="margin: 0; padding: 0; background-color: #030712; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; color: #f8fafc;">
    <table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="background-color: #030712; padding: 40px 15px;">
        <tr>
            <td align="center">
                <table role="presentation" width="100%" style="max-width: 520px; background: #0f172a; border: 1px solid #1e293b; border-radius: 16px; overflow: hidden; box-shadow: 0 10px 30px rgba(0,0,0,0.5);" cellspacing="0" cellpadding="0">
                    <!-- Header -->
                    <tr>
                        <td style="padding: 32px 32px 20px 32px; text-align: center; background: linear-gradient(180deg, #1e293b 0%, #0f172a 100%);">
                            <div style="font-size: 36px; margin-bottom: 8px;">🧠</div>
                            <h1 style="margin: 0; font-size: 22px; font-weight: 800; color: #f8fafc; letter-spacing: -0.02em;">
                                Multi-Agent Orchestrator
                            </h1>
                            <p style="margin: 6px 0 0 0; font-size: 13px; color: #94a3b8;">
                                Secure Email Authentication
                            </p>
                        </td>
                    </tr>
                    <!-- Body -->
                    <tr>
                        <td style="padding: 24px 32px;">
                            <p style="font-size: 15px; color: #cbd5e1; line-height: 1.6; margin: 0 0 20px 0;">
                                You requested to sign in to your Multi-Agent Orchestrator workspace. Use the one-time verification code below to complete your login:
                            </p>
                            
                            <!-- OTP Code Box -->
                            <div style="background: #030712; border: 1px solid #3b82f6; border-radius: 12px; padding: 22px; text-align: center; margin: 24px 0;">
                                <div style="font-size: 12px; font-weight: 600; text-transform: uppercase; letter-spacing: 0.1em; color: #60a5fa; margin-bottom: 8px;">
                                    One-Time Passcode
                                </div>
                                <span style="font-family: 'SF Mono', Consolas, 'Liberation Mono', Menlo, Courier, monospace; font-size: 34px; font-weight: 800; letter-spacing: 8px; color: #ffffff; text-shadow: 0 0 12px rgba(59, 130, 246, 0.5);">
                                    {otp_code}
                                </span>
                            </div>

                            <p style="font-size: 13px; color: #94a3b8; line-height: 1.5; margin: 0 0 16px 0;">
                                ⏱️ This code will expire in <strong style="color: #f8fafc;">{expiry_mins} minutes</strong>.
                            </p>
                            <p style="font-size: 12px; color: #64748b; line-height: 1.5; margin: 0;">
                                🔒 If you did not initiate this login request, please disregard this email. Never share this code with anyone.
                            </p>
                        </td>
                    </tr>
                    <!-- Footer -->
                    <tr>
                        <td style="padding: 20px 32px; background-color: #0b1120; border-top: 1px solid #1e293b; text-align: center;">
                            <p style="margin: 0; font-size: 11px; color: #475569;">
                                Powered by Google SMTP • Multi-Agent Orchestrator Engine
                            </p>
                        </td>
                    </tr>
                </table>
            </td>
        </tr>
    </table>
</body>
</html>
"""
        msg.attach(MIMEText(text_content, "plain", "utf-8"))
        msg.attach(MIMEText(html_content, "html", "utf-8"))
        return msg

    def send_otp(self, email: str) -> Tuple[bool, str, Optional[str]]:
        """
        Generates and sends an OTP to the given email address.
        Returns (success: bool, message: str, dev_code_preview: Optional[str]).
        """
        email = email.strip().lower()
        if not self.is_valid_email(email):
            return False, "Please provide a valid email address (e.g. user@example.com).", None

        now = time.time()

        with self._lock:
            # Rate limiting: max 1 email every 30 seconds
            last_time = self._last_sent.get(email, 0)
            if now - last_time < 30:
                wait_sec = int(30 - (now - last_time))
                return False, f"Please wait {wait_sec}s before requesting another verification code.", None

            otp_code = self._generate_otp()
            self._otp_store[email] = {
                "code": otp_code,
                "expires_at": now + self.otp_expiry_seconds,
                "attempts": 0,
                "created_at": now
            }
            self._last_sent[email] = now

        # If SMTP is configured, send via Google SMTP
        if self.is_smtp_configured():
            try:
                msg = self._create_email_message(email, otp_code)
                server = smtplib.SMTP(self.smtp_host, self.smtp_port, timeout=15)
                try:
                    server.ehlo()
                    server.starttls()
                    server.ehlo()
                    server.login(self.smtp_user, self.smtp_password)
                    server.send_message(msg)
                finally:
                    try:
                        server.quit()
                    except Exception:
                        pass
                return True, f"Verification code sent to {email}. Please check your inbox.", None
            except Exception as e:
                return False, f"Failed to send email via Google SMTP: {str(e)}", None
        else:
            # Dev Fallback mode if SMTP credentials are not yet set
            return (
                True,
                f"[Dev Mode] Code generated for {email}! (Configure SMTP in .env for live email delivery)",
                otp_code
            )

    def verify_otp(self, email: str, user_code: str) -> Tuple[bool, str]:
        """
        Verifies the user-supplied OTP code against stored records.
        Returns (success: bool, message: str).
        """
        email = email.strip().lower()
        user_code = user_code.strip()

        if not email or not user_code:
            return False, "Email and verification code are required."

        if not self.is_valid_email(email):
            return False, "Invalid email address format."

        with self._lock:
            record = self._otp_store.get(email)
            if not record:
                return False, "No active verification code found for this email. Please click 'Send Code'."

            now = time.time()
            if now > record["expires_at"]:
                del self._otp_store[email]
                return False, "Verification code has expired. Please request a new one."

            if record["attempts"] >= self.max_attempts:
                del self._otp_store[email]
                return False, "Maximum verification attempts exceeded. Please request a new code."

            record["attempts"] += 1

            # Constant-time comparison to prevent timing attacks
            if secrets.compare_digest(record["code"], user_code):
                # Consume the OTP once verified
                del self._otp_store[email]
                return True, "Login verified successfully! Welcome to Multi-Agent Orchestrator."

            remaining = self.max_attempts - record["attempts"]
            return False, f"Incorrect verification code. ({remaining} attempts remaining)"

    def clear_session(self, email: str) -> None:
        """Clears any stored OTP data for the email."""
        email = email.strip().lower()
        with self._lock:
            self._otp_store.pop(email, None)
            self._last_sent.pop(email, None)


# Global singleton instance
auth_manager = EmailAuthManager()
