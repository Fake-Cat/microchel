"""База LLM-провайдеров (PHASE 5): ошибки и интерфейс адаптера.

Ошибки разделены по типам, чтобы executor мог различать конец (rate limit),
инфраструктуру (сеть) и протокол (изменение API).
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol

from microchel.agent.types import LLMMessage, LLMResponse
from microchel.tools.base import ToolSpec


class LLMError(Exception):
    """Базовая ошибка LLM-провайдера."""


class LLMNetworkError(LLMError):
    """Сеть/таймаут: провайдер недоступен."""


class LLMAuthError(LLMError):
    """401/403: неверный или отозванный API-ключ."""


class LLMRateLimitError(LLMError):
    """429: квота исчерпана, повтор позже."""


class LLMProtocolError(LLMError):
    """Неожиданный формат ответа или 4xx-ошибка запроса."""


class LLMProvider(Protocol):
    """Интерфейс адаптера LLM: полный диалог → текст и/или tool calls."""

    name: str

    def complete(
        self, messages: Sequence[LLMMessage], tools: Sequence[ToolSpec]
    ) -> LLMResponse: ...