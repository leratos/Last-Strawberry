import unittest
from unittest.mock import Mock, patch

import httpx

from backend_v2.app.config import Settings
from backend_v2.app.providers.embeddings_openrouter import OpenRouterEmbeddingsProvider
from backend_v2.app.services.embeddings import EmbeddingsProviderError


class TestOpenRouterEmbeddingsProvider(unittest.TestCase):
    def test_embed_texts_success(self):
        settings = Settings(
            openrouter_api_key="test-key",
            openrouter_base_url="https://openrouter.ai/api/v1",
            embeddings_model="openai/text-embedding-3-small",
            embeddings_timeout_seconds=10,
            openrouter_site_url="https://example.org",
            openrouter_site_name="ls-v2",
        )
        client = Mock()
        request = httpx.Request("POST", "https://openrouter.ai/api/v1/embeddings")
        response = httpx.Response(
            status_code=200,
            json={
                "data": [
                    {"embedding": [0.1, 0.2]},
                    {"embedding": [0.3, 0.4]},
                ]
            },
            request=request,
        )
        client.post.return_value = response

        provider = OpenRouterEmbeddingsProvider(settings=settings, client=client)
        self.assertEqual(provider.model_name, "openai/text-embedding-3-small")
        vectors = provider.embed_texts(["alpha", "beta"])

        self.assertEqual(vectors, [[0.1, 0.2], [0.3, 0.4]])
        client.post.assert_called_once()
        _, kwargs = client.post.call_args
        self.assertIn("Authorization", kwargs["headers"])
        self.assertEqual(kwargs["json"]["model"], "openai/text-embedding-3-small")
        self.assertEqual(kwargs["json"]["input"], ["alpha", "beta"])

    def test_embed_texts_empty_input(self):
        settings = Settings(openrouter_api_key="test-key")
        provider = OpenRouterEmbeddingsProvider(settings=settings, client=Mock())
        self.assertEqual(provider.embed_texts([]), [])

    def test_embed_texts_raises_without_api_key(self):
        settings = Settings(openrouter_api_key=None)
        provider = OpenRouterEmbeddingsProvider(settings=settings, client=Mock())
        with self.assertRaises(EmbeddingsProviderError):
            provider.embed_texts(["alpha"])

    def test_embed_texts_raises_on_http_error(self):
        settings = Settings(openrouter_api_key="test-key")
        client = Mock()
        request = httpx.Request("POST", "https://openrouter.ai/api/v1/embeddings")
        response = httpx.Response(status_code=401, text="unauthorized", request=request)
        client.post.return_value = response

        provider = OpenRouterEmbeddingsProvider(settings=settings, client=client)
        with self.assertRaises(EmbeddingsProviderError) as context:
            provider.embed_texts(["alpha"])
        self.assertIn("HTTP error", str(context.exception))

    def test_embed_texts_http_error_redacts_sensitive_fields(self):
        settings = Settings(openrouter_api_key="test-key")
        client = Mock()
        request = httpx.Request("POST", "https://openrouter.ai/api/v1/embeddings")
        response = httpx.Response(
            status_code=401,
            text='Authorization: Bearer hidden-token {"token":"abc123"}',
            request=request,
        )
        client.post.return_value = response

        provider = OpenRouterEmbeddingsProvider(settings=settings, client=client)
        with self.assertRaises(EmbeddingsProviderError) as context:
            provider.embed_texts(["alpha"])

        message = str(context.exception)
        self.assertIn("401", message)
        self.assertNotIn("hidden-token", message)
        self.assertNotIn("abc123", message)
        self.assertIn("[REDACTED]", message)

    def test_embed_texts_raises_on_invalid_response_shape(self):
        settings = Settings(openrouter_api_key="test-key")
        client = Mock()
        request = httpx.Request("POST", "https://openrouter.ai/api/v1/embeddings")
        response = httpx.Response(
            status_code=200,
            json={"data": [{"embedding": [0.1, 0.2]}]},
            request=request,
        )
        client.post.return_value = response

        provider = OpenRouterEmbeddingsProvider(settings=settings, client=client)
        with self.assertRaises(EmbeddingsProviderError):
            provider.embed_texts(["alpha", "beta"])

    def test_embed_texts_timeout_maps_to_embeddings_error(self):
        settings = Settings(openrouter_api_key="test-key")
        client = Mock()
        client.post.side_effect = httpx.TimeoutException("timeout")

        provider = OpenRouterEmbeddingsProvider(settings=settings, client=client)
        with self.assertRaises(EmbeddingsProviderError) as context:
            provider.embed_texts(["alpha"])
        self.assertIn("timed out", str(context.exception))

    def test_embed_texts_invalid_response_format(self):
        settings = Settings(openrouter_api_key="test-key")
        client = Mock()
        request = httpx.Request("POST", "https://openrouter.ai/api/v1/embeddings")
        response = httpx.Response(status_code=200, json={"unexpected": []}, request=request)
        client.post.return_value = response

        provider = OpenRouterEmbeddingsProvider(settings=settings, client=client)
        with self.assertRaises(EmbeddingsProviderError) as context:
            provider.embed_texts(["alpha"])
        self.assertIn("Invalid OpenRouter embeddings response format", str(context.exception))

    def test_embed_texts_uses_internal_httpx_client_when_not_injected(self):
        settings = Settings(
            openrouter_api_key="test-key",
            embeddings_model="openai/text-embedding-3-small",
            embeddings_timeout_seconds=5,
        )
        request = httpx.Request("POST", "https://openrouter.ai/api/v1/embeddings")
        response = httpx.Response(status_code=200, json={"data": [{"embedding": [0.1, 0.2]}]}, request=request)

        fake_client = Mock()
        fake_client.post.return_value = response

        with patch("backend_v2.app.providers.embeddings_openrouter.httpx.Client") as client_cls:
            client_cls.return_value.__enter__.return_value = fake_client
            provider = OpenRouterEmbeddingsProvider(settings=settings, client=None)
            vectors = provider.embed_texts(["alpha"])

        self.assertEqual(vectors, [[0.1, 0.2]])
        fake_client.post.assert_called_once()

    def test_embed_texts_generic_exception_maps_to_embeddings_error(self):
        settings = Settings(openrouter_api_key="test-key")
        client = Mock()
        client.post.side_effect = ValueError("boom")

        provider = OpenRouterEmbeddingsProvider(settings=settings, client=client)
        with self.assertRaises(EmbeddingsProviderError) as context:
            provider.embed_texts(["alpha"])
        self.assertIn("request failed", str(context.exception))


if __name__ == "__main__":
    unittest.main()
