from abc import ABC, abstractmethod


class ProviderError(RuntimeError):
    pass


class LLMProvider(ABC):
    name: str = "unknown"

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
