"""FakeProvider (PHASE 5): офлайн-провайдер для тестов и --offline.

Отдаёт заготовленные LLMResponse по очереди и пишет историю вызовов —
исполнитель проверяется без сети и без API-ключа.
"""

from __future__ import annotations

from collections.abc import Sequence

from microchel.agent.types import LLMMessage, LLMResponse
from microchel.tools.base import ToolSpec


class FakeProvider:
    """Сценарный LLM: заранее заданные ответы, история вызовов в self.calls."""

    name = "fake"

    def __init__(self, responses: Sequence[LLMResponse] | None = None) -> None:
        self._responses = list(responses or ())
        self.calls: list[tuple[tuple[LLMMessage, ...], tuple[ToolSpec, ...]]] = []

    def complete(self, messages: Sequence[LLMMessage], tools: Sequence[ToolSpec]) -> LLMResponse:
        self.calls.append((tuple(messages), tuple(tools)))
        if self._responses:
            return self._responses.pop(0)
        return LLMResponse(text="Готово (офлайн-провайдер без сценария).", tool_calls=())

    @property
    def remaining(self) -> int:
        return len(self._responses)