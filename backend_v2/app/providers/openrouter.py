import httpx

from backend_v2.app.config import Settings
from backend_v2.app.providers.base import LLMProvider, ProviderError
from backend_v2.app.security import redact_sensitive_text


class OpenRouterProvider(LLMProvider):
    name = "openrouter"

    def __init__(self, settings: Settings, client: httpx.AsyncClient | None = None):
        self.settings = settings
        self._client = client

    def _build_headers(self) -> dict[str, str]:
        if not self.settings.openrouter_api_key:
            raise ProviderError("LS_OPENROUTER_API_KEY is not configured.")

        headers = {
            "Authorization": f"Bearer {self.settings.openrouter_api_key}",
            "Content-Type": "application/json",
        }
        if self.settings.openrouter_site_url:
            headers["HTTP-Referer"] = self.settings.openrouter_site_url
        if self.settings.openrouter_site_name:
            headers["X-Title"] = self.settings.openrouter_site_name
        return headers

    def _build_payload(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        model: str,
        temperature: float,
        max_tokens: int,
    ) -> dict:
        return {
            "model": model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": temperature,
            "max_tokens": max_tokens,
        }

    async def generate(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        model: str,
        temperature: float,
        max_tokens: int,
    ) -> str:
        headers = self._build_headers()
        payload = self._build_payload(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
        )
        url = f"{self.settings.openrouter_base_url.rstrip('/')}/chat/completions"

        try:
            if self._client is not None:
                response = await self._client.post(url, headers=headers, json=payload)
            else:
                async with httpx.AsyncClient(timeout=self.settings.request_timeout_seconds) as client:
                    response = await client.post(url, headers=headers, json=payload)
            response.raise_for_status()
            data = response.json()
        except httpx.TimeoutException as exc:
            raise ProviderError("OpenRouter request timed out.") from exc
        except httpx.HTTPError as exc:
            status = getattr(exc.response, "status_code", "unknown")
            body = getattr(exc.response, "text", "")
            raise ProviderError(f"OpenRouter HTTP error {status}: {redact_sensitive_text(body, max_length=240)}") from exc
        except Exception as exc:
            raise ProviderError(f"OpenRouter request failed: {redact_sensitive_text(exc, max_length=180)}") from exc

        try:
            return data["choices"][0]["message"]["content"].strip()
        except Exception as exc:
            raise ProviderError("Invalid OpenRouter response format.") from exc
