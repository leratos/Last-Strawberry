import unittest

from backend_v2.app.security import redact_sensitive_text, sanitize_for_log


class TestSecurityHelpers(unittest.TestCase):
    def test_sanitize_for_log_collapses_whitespace_and_truncates(self):
        value = "line1\nline2\tline3"
        sanitized = sanitize_for_log(value, max_length=12)
        self.assertEqual(sanitized, "line1 line2 ...")

    def test_redact_sensitive_text_hides_bearer_and_api_key(self):
        text = 'Authorization: Bearer secret-token-123, {"api_key":"super-secret"}'
        redacted = redact_sensitive_text(text)
        self.assertNotIn("secret-token-123", redacted)
        self.assertNotIn("super-secret", redacted)
        self.assertIn("[REDACTED]", redacted)


if __name__ == "__main__":
    unittest.main()
