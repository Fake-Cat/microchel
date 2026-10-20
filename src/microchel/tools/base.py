"""Базовые типы инструментов агента (PHASE 5): спецификации и результаты.

Tool-спецификация соответствует формату function declarations Gemini
(JSON Schema subset): name/description/parameters.properties/required.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol


class ToolError(Exception):
    """Базовая ошибка инструмента (не роняет задачу агента)."""


class ToolDenied(ToolError):
    """Операция запрещена политикой (PathGuard, валидация имени и т.п.)."""


class ToolInvalid(ToolError):
    """Некорректные аргументы вызова."""


@dataclass(frozen=True, slots=True)
class ToolSpec:
    """Спецификация инструмента для LLM (name/description/JSON Schema)."""

    name: str
    description: str
    parameters: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class ToolResult:
    """Результат вызова инструмента; ошибка — значение, не исключение."""

    ok: bool
    data: Any = None
    error: str = ""


class Tool(Protocol):
    """Интерфейс инструмента: спецификация + синхронное выполнение."""

    def spec(self) -> ToolSpec: ...

    def execute(self, arguments: dict[str, Any]) -> ToolResult: ...