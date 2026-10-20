"""LLM-провайдеры Agent Core (PHASE 5): gemini (сеть) и fake (офлайн).

build_provider — фабрика из AgentConfig: провайдер выбирается конфигом/CLI,
ключ берётся только из окружения, прокси резолвится по правилам ADR-006.
"""

from microchel.agent.config import AgentConfig, resolve_proxy_url
from microchel.agent.llm.base import (
    LLMAuthError,
    LLMError,
    LLMNetworkError,
    LLMProtocolError,
    LLMProvider,
    LLMRateLimitError,
)
from microchel.agent.llm.fake import FakeProvider
from microchel.agent.llm.gemini import GeminiProvider
from microchel.agent.llm.http import HttpClient

__all__ = [
    "FakeProvider",
    "GeminiProvider",
    "HttpClient",
    "LLMAuthError",
    "LLMError",
    "LLMNetworkError",
    "LLMProtocolError",
    "LLMProvider",
    "LLMRateLimitError",
    "build_provider",
]


def build_provider(
    config: AgentConfig,
    *,
    provider_name: str | None = None,
    model: str | None = None,
    proxy_url: str | None = None,
) -> LLMProvider:
    """Создать провайдера по конфигу; fake — без ключа и без сети."""
    name = provider_name or config.provider
    if name == "fake":
        return FakeProvider()
    if name == "gemini":
        return GeminiProvider(
            api_key=config.api_key(),
            model=model or config.model,
            proxy_url=resolve_proxy_url(proxy_url, config.proxy_url),
            base_url=config.base_url,
        )
    raise ValueError(f"неизвестный LLM-провайдер: {name!r} (ожидаются gemini, fake)")