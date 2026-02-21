import unittest
from unittest.mock import patch

import httpx

from backend_v2.app.config import Settings
from backend_v2.app.providers.base import ProviderError
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

    def test_build_headers_without_key_raises(self):
        settings = Settings(openrouter_api_key=None)
        provider = OpenRouterProvider(settings)
        with self.assertRaises(ProviderError):
            provider._build_headers()


class _FakeResponse:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self._payload


class _FakeClient:
    def __init__(self, response=None, exception=None):
        self._response = response
        self._exception = exception

    async def post(self, url, headers, json):
        if self._exception:
            raise self._exception
        return self._response


class _FakeAsyncClientContext:
    def __init__(self, response):
        self._response = response

    async def __aenter__(self):
        return _FakeClient(response=self._response)

    async def __aexit__(self, exc_type, exc, tb):
        return False


class TestOpenRouterProviderAsync(unittest.IsolatedAsyncioTestCase):
    async def test_generate_result_includes_usage_tokens_and_cost(self):
        settings = Settings(openrouter_api_key="k")
        response = _FakeResponse(
            {
                "choices": [{"message": {"content": "Antwort"}}],
                "usage": {
                    "prompt_tokens": 12,
                    "completion_tokens": 34,
                    "total_tokens": 46,
                    "cost": 0.00123,
                },
            }
        )
        provider = OpenRouterProvider(settings, client=_FakeClient(response=response))

        result = await provider.generate_result(
            system_prompt="sys",
            user_prompt="user",
            model="m",
            temperature=0.2,
            max_tokens=200,
        )
        self.assertEqual(result.text, "Antwort")
        self.assertEqual(result.usage.prompt_tokens, 12)
        self.assertEqual(result.usage.completion_tokens, 34)
        self.assertEqual(result.usage.total_tokens, 46)
        self.assertEqual(result.usage.provider_reported_cost_usd, 0.00123)
        self.assertGreaterEqual(result.latency_ms, 0.0)

    async def test_generate_success_with_injected_client(self):
        settings = Settings(openrouter_api_key="k")
        response = _FakeResponse({"choices": [{"message": {"content": "  Hallo Welt  "}}]})
        provider = OpenRouterProvider(settings, client=_FakeClient(response=response))

        result = await provider.generate(
            system_prompt="sys",
            user_prompt="user",
            model="m",
            temperature=0.2,
            max_tokens=200,
        )
        self.assertEqual(result, "Hallo Welt")

    async def test_generate_timeout_maps_to_provider_error(self):
        settings = Settings(openrouter_api_key="k")
        provider = OpenRouterProvider(
            settings,
            client=_FakeClient(exception=httpx.TimeoutException("timeout")),
        )

        with self.assertRaises(ProviderError) as ctx:
            await provider.generate(
                system_prompt="sys",
                user_prompt="user",
                model="m",
                temperature=0.2,
                max_tokens=200,
            )
        self.assertIn("timed out", str(ctx.exception))

    async def test_generate_http_error_maps_status_and_body(self):
        settings = Settings(openrouter_api_key="k")
        request = httpx.Request("POST", "https://example.test")
        response = httpx.Response(429, request=request, text="rate-limited")
        http_error = httpx.HTTPStatusError("bad status", request=request, response=response)
        provider = OpenRouterProvider(settings, client=_FakeClient(exception=http_error))

        with self.assertRaises(ProviderError) as ctx:
            await provider.generate(
                system_prompt="sys",
                user_prompt="user",
                model="m",
                temperature=0.2,
                max_tokens=200,
            )
        self.assertIn("429", str(ctx.exception))
        self.assertIn("rate-limited", str(ctx.exception))

    async def test_generate_http_error_redacts_sensitive_fields(self):
        settings = Settings(openrouter_api_key="k")
        request = httpx.Request("POST", "https://example.test")
        response = httpx.Response(
            401,
            request=request,
            text='Authorization: Bearer super-secret-token api_key=secret123',
        )
        http_error = httpx.HTTPStatusError("bad status", request=request, response=response)
        provider = OpenRouterProvider(settings, client=_FakeClient(exception=http_error))

        with self.assertRaises(ProviderError) as ctx:
            await provider.generate(
                system_prompt="sys",
                user_prompt="user",
                model="m",
                temperature=0.2,
                max_tokens=200,
            )
        message = str(ctx.exception)
        self.assertIn("401", message)
        self.assertNotIn("super-secret-token", message)
        self.assertNotIn("secret123", message)
        self.assertIn("[REDACTED]", message)

    async def test_generate_invalid_payload_raises_provider_error(self):
        settings = Settings(openrouter_api_key="k")
        provider = OpenRouterProvider(settings, client=_FakeClient(response=_FakeResponse({"foo": "bar"})))

        with self.assertRaises(ProviderError) as ctx:
            await provider.generate(
                system_prompt="sys",
                user_prompt="user",
                model="m",
                temperature=0.2,
                max_tokens=200,
            )
        self.assertIn("Invalid OpenRouter response format", str(ctx.exception))

    async def test_generate_unknown_exception_maps_to_provider_error(self):
        settings = Settings(openrouter_api_key="k")
        provider = OpenRouterProvider(settings, client=_FakeClient(exception=RuntimeError("broken")))

        with self.assertRaises(ProviderError) as ctx:
            await provider.generate(
                system_prompt="sys",
                user_prompt="user",
                model="m",
                temperature=0.2,
                max_tokens=200,
            )
        self.assertIn("request failed", str(ctx.exception))

    async def test_generate_success_with_internal_async_client_context(self):
        settings = Settings(openrouter_api_key="k")
        response = _FakeResponse({"choices": [{"message": {"content": "Antwort"}}]})
        provider = OpenRouterProvider(settings, client=None)

        with patch(
            "backend_v2.app.providers.openrouter.httpx.AsyncClient",
            return_value=_FakeAsyncClientContext(response=response),
        ):
            result = await provider.generate(
                system_prompt="sys",
                user_prompt="user",
                model="m",
                temperature=0.2,
                max_tokens=200,
            )
        self.assertEqual(result, "Antwort")


if __name__ == "__main__":
    unittest.main()
