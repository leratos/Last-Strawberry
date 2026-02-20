import unittest

from backend_v2.app.security import parse_content_length_header, redact_sensitive_text, sanitize_for_log


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

    def test_parse_content_length_header(self):
        self.assertIsNone(parse_content_length_header(None))
        self.assertIsNone(parse_content_length_header(""))
        self.assertEqual(parse_content_length_header("0"), 0)
        self.assertEqual(parse_content_length_header("42"), 42)

    def test_parse_content_length_header_rejects_invalid_values(self):
        with self.assertRaises(ValueError):
            parse_content_length_header("-1")
        with self.assertRaises(ValueError):
            parse_content_length_header("abc")


if __name__ == "__main__":
    unittest.main()
