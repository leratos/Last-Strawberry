import httpx

from backend_v2.app.config import Settings
from backend_v2.app.services.embeddings import EmbeddingsProviderError


class OpenRouterEmbeddingsProvider:
    provider_name = "openrouter"

    def __init__(self, settings: Settings, client: httpx.Client | None = None):
        self.settings = settings
        self._client = client

    def _build_headers(self) -> dict[str, str]:
        if not self.settings.openrouter_api_key:
            raise EmbeddingsProviderError("LS_OPENROUTER_API_KEY is not configured for embeddings.")

        headers = {
            "Authorization": f"Bearer {self.settings.openrouter_api_key}",
            "Content-Type": "application/json",
        }
        if self.settings.openrouter_site_url:
            headers["HTTP-Referer"] = self.settings.openrouter_site_url
        if self.settings.openrouter_site_name:
            headers["X-Title"] = self.settings.openrouter_site_name
        return headers

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []

        headers = self._build_headers()
        url = f"{self.settings.openrouter_base_url.rstrip('/')}/embeddings"
        payload = {
            "model": self.settings.embeddings_model,
            "input": texts,
        }

        try:
            if self._client is not None:
                response = self._client.post(url, headers=headers, json=payload)
            else:
                with httpx.Client(timeout=self.settings.embeddings_timeout_seconds) as client:
                    response = client.post(url, headers=headers, json=payload)
            response.raise_for_status()
            data = response.json()
        except httpx.TimeoutException as exc:
            raise EmbeddingsProviderError("OpenRouter embeddings request timed out.") from exc
        except httpx.HTTPError as exc:
            status = getattr(exc.response, "status_code", "unknown")
            body = getattr(exc.response, "text", "")
            raise EmbeddingsProviderError(f"OpenRouter embeddings HTTP error {status}: {body}") from exc
        except Exception as exc:
            raise EmbeddingsProviderError(f"OpenRouter embeddings request failed: {exc}") from exc

        try:
            rows = data["data"]
            embeddings = [row["embedding"] for row in rows]
            if len(embeddings) != len(texts):
                raise EmbeddingsProviderError(
                    f"OpenRouter embeddings count mismatch: expected {len(texts)}, got {len(embeddings)}"
                )
            return [[float(value) for value in row] for row in embeddings]
        except EmbeddingsProviderError:
            raise
        except Exception as exc:
            raise EmbeddingsProviderError(f"Invalid OpenRouter embeddings response format: {data}") from exc
