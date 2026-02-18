import unittest

from backend_v2.app.config import Settings
from backend_v2.app.providers.openrouter import OpenRouterProvider


class TestOpenRouterProvider(unittest.TestCase):
    def test_build_payload_has_expected_shape(self):
        settings = Settings(openrouter_api_key="test-key")
        provider = OpenRouterProvider(settings)

        payload = provider._build_payload(
            system_prompt="system",
            user_prompt="user",
            model="openrouter/model",
            temperature=0.2,
            max_tokens=300,
        )

        self.assertEqual(payload["model"], "openrouter/model")
        self.assertEqual(payload["messages"][0]["role"], "system")
        self.assertEqual(payload["messages"][1]["role"], "user")
        self.assertEqual(payload["temperature"], 0.2)
        self.assertEqual(payload["max_tokens"], 300)

    def test_build_headers_requires_api_key(self):
        settings = Settings(openrouter_api_key="abc123", openrouter_site_url="http://localhost:8002")
        provider = OpenRouterProvider(settings)
        headers = provider._build_headers()
        self.assertIn("Authorization", headers)
        self.assertIn("HTTP-Referer", headers)


if __name__ == "__main__":
    unittest.main()
