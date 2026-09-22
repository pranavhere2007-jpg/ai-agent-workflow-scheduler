import unittest
import time
import os
from unittest.mock import patch, MagicMock
from auth_service import EmailAuthManager

class TestEmailAuthManager(unittest.TestCase):
    def setUp(self):
        self.auth = EmailAuthManager()

    def test_email_validation(self):
        self.assertTrue(self.auth.is_valid_email("user@example.com"))
        self.assertTrue(self.auth.is_valid_email("test.name+tag@gmail.com"))
        self.assertFalse(self.auth.is_valid_email("invalid-email"))
        self.assertFalse(self.auth.is_valid_email("@no-user.com"))
        self.assertFalse(self.auth.is_valid_email(""))

    def test_otp_generation_and_verification(self):
        email = "testuser@gmail.com"
        # In dev mode without env SMTP credentials, send_otp returns dev preview code
        success, msg, dev_code = self.auth.send_otp(email)
        self.assertTrue(success)
        self.assertIsNotNone(dev_code)
        self.assertEqual(len(dev_code), 6)
        self.assertTrue(dev_code.isdigit())

        # Test invalid OTP
        verified, err_msg = self.auth.verify_otp(email, "000000" if dev_code != "000000" else "111111")
        self.assertFalse(verified)

        # Test valid OTP
        verified, ok_msg = self.auth.verify_otp(email, dev_code)
        self.assertTrue(verified)

        # Once verified, it should be consumed and cannot be reused
        reused, reuse_msg = self.auth.verify_otp(email, dev_code)
        self.assertFalse(reused)

    def test_otp_expiry(self):
        email = "expire_test@gmail.com"
        # Directly expire the record in store
        success, msg, code = self.auth.send_otp(email)
        self.assertTrue(success)
        self.auth._otp_store[email]["expires_at"] = time.time() - 1

        verified, err_msg = self.auth.verify_otp(email, code)
        self.assertFalse(verified)
        self.assertIn("expired", err_msg.lower())

    def test_max_attempts_lockout(self):
        email = "lockout_test@gmail.com"
        success, msg, code = self.auth.send_otp(email)
        self.assertTrue(success)

        wrong_code = "999999" if code != "999999" else "888888"
        for _ in range(self.auth.max_attempts):
            verified, _ = self.auth.verify_otp(email, wrong_code)
            self.assertFalse(verified)

        # Should be locked out / removed
        verified, lock_msg = self.auth.verify_otp(email, code)
        self.assertFalse(verified)

    @patch("smtplib.SMTP")
    def test_smtp_send_success(self, mock_smtp_cls):
        mock_server = MagicMock()
        mock_smtp_cls.return_value = mock_server

        # Simulate configured credentials in os.environ
        with patch.dict(os.environ, {
            "SMTP_HOST": "smtp.gmail.com",
            "SMTP_PORT": "587",
            "SMTP_USER": "sender@gmail.com",
            "SMTP_PASSWORD": "secret_app_password",
            "SMTP_SENDER_NAME": "Test App"
        }):
            email = "recipient@example.com"
            success, msg, dev_code = self.auth.send_otp(email)
            self.assertTrue(success)
            self.assertIsNone(dev_code)
            self.assertIn("Verification code sent", msg)
            
            mock_server.starttls.assert_called_once()
            mock_server.login.assert_called_once_with('sender@gmail.com', 'secret_app_password')
            mock_server.send_message.assert_called_once()

if __name__ == "__main__":
    unittest.main()
