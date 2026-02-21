import httpx
from time import perf_counter

from backend_v2.app.config import Settings
from backend_v2.app.providers.base import GenerationResult, GenerationUsage, LLMProvider, ProviderError
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

    @staticmethod
    def _to_non_negative_int(value: object) -> int:
        try:
            parsed = int(value)
        except (TypeError, ValueError):
            return 0
        return parsed if parsed > 0 else 0

    @staticmethod
    def _to_non_negative_float(value: object) -> float | None:
        if value is None:
            return None
        try:
            parsed = float(value)
        except (TypeError, ValueError):
            return None
        return parsed if parsed >= 0.0 else None

    def _extract_usage(self, data: dict) -> GenerationUsage:
        usage_payload = data.get("usage", {})
        if not isinstance(usage_payload, dict):
            usage_payload = {}

        prompt_tokens = self._to_non_negative_int(usage_payload.get("prompt_tokens"))
        completion_tokens = self._to_non_negative_int(usage_payload.get("completion_tokens"))
        total_tokens = self._to_non_negative_int(usage_payload.get("total_tokens"))
        if total_tokens <= 0:
            total_tokens = prompt_tokens + completion_tokens

        provider_cost = self._to_non_negative_float(usage_payload.get("cost"))
        if provider_cost is None:
            provider_cost = self._to_non_negative_float(data.get("total_cost"))

        return GenerationUsage(
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=total_tokens,
            provider_reported_cost_usd=provider_cost,
        )

    async def generate_result(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        model: str,
        temperature: float,
        max_tokens: int,
    ) -> GenerationResult:
        started_at = perf_counter()
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
            text = data["choices"][0]["message"]["content"].strip()
        except Exception as exc:
            raise ProviderError("Invalid OpenRouter response format.") from exc

        usage = self._extract_usage(data)
        return GenerationResult(
            text=text,
            model=model,
            latency_ms=(perf_counter() - started_at) * 1000.0,
            usage=usage,
        )

    async def generate(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        model: str,
        temperature: float,
        max_tokens: int,
    ) -> str:
        result = await self.generate_result(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
        )
        return result.text
