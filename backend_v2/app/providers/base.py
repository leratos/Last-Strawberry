from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from time import perf_counter


@dataclass(frozen=True)
class GenerationUsage:
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    provider_reported_cost_usd: float | None = None


@dataclass(frozen=True)
class GenerationResult:
    text: str
    model: str
    latency_ms: float
    usage: GenerationUsage = field(default_factory=GenerationUsage)


class ProviderError(RuntimeError):
    pass


class LLMProvider(ABC):
    name: str = "unknown"

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
        text = await self.generate(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
        )
        return GenerationResult(
            text=text,
            model=model,
            latency_ms=(perf_counter() - started_at) * 1000.0,
        )

    @abstractmethod
    async def generate(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        model: str,
        temperature: float,
        max_tokens: int,
    ) -> str:
        raise NotImplementedError
