"""Реестр инструментов агента (PHASE 5): валидация, таймауты, ошибки-значения.

execute() никогда не бросает исключений наружу: неизвестный инструмент,
невалидные аргументы, падение/таймаут инструмента → ToolResult(ok=False).
"""

from __future__ import annotations

import logging
import threading
from collections.abc import Iterable
from typing import Any

from microchel.tools.base import Tool, ToolResult, ToolSpec

logger = logging.getLogger(__name__)

_TYPE_MAP: dict[str, tuple[type, ...]] = {
    "string": (str,),
    "integer": (int,),
    "number": (int, float),
    "boolean": (bool,),
    "object": (dict,),
    "array": (list,),
}


def _type_ok(value: Any, expected: str) -> bool:
    if expected == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if expected == "number":
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    types = _TYPE_MAP.get(expected)
    return types is None or isinstance(value, types)


def _validate(spec: ToolSpec, arguments: Any) -> str:
    """Мини-валидация по JSON Schema subset; "" — ок, иначе текст ошибки."""
    if not isinstance(arguments, dict):
        return "аргументы должны быть JSON-объектом"
    schema = spec.parameters or {}
    properties: dict[str, Any] = schema.get("properties", {}) or {}
    required: Iterable[str] = schema.get("required", []) or []
    for key in required:
        if key not in arguments:
            return f"нет обязательного аргумента '{key}'"
    for key, value in arguments.items():
        if key not in properties:
            return f"неизвестный аргумент '{key}'"
        expected = (properties[key] or {}).get("type")
        if expected and not _type_ok(value, expected):
            return f"аргумент '{key}': ожидается тип {expected}"
    return ""


class ToolRegistry:
    """Реестр инструментов: имя → Tool, спецификации для LLM, безопасный вызов."""

    def __init__(self) -> None:
        self._tools: dict[str, Tool] = {}

    def register(self, tool: Tool) -> None:
        name = tool.spec().name
        if not name or name in self._tools:
            raise ValueError(f"инструмент с именем {name!r} уже зарегистрирован или безымянный")
        self._tools[name] = tool

    def specs(self) -> tuple[ToolSpec, ...]:
        return tuple(tool.spec() for tool in self._tools.values())

    def names(self) -> tuple[str, ...]:
        return tuple(self._tools)

    def execute(
        self, name: str, arguments: dict[str, Any], *, timeout_s: float = 15.0
    ) -> ToolResult:
        """Вызвать инструмент с валидацией и таймаутом; исключения не уходят наружу."""
        tool = self._tools.get(name)
        if tool is None:
            return ToolResult(ok=False, error=f"неизвестный инструмент '{name}'")
        spec = tool.spec()
        problem = _validate(spec, arguments)
        if problem:
            return ToolResult(ok=False, error=f"некорректные аргументы: {problem}")

        box: dict[str, Any] = {}

        def _run() -> None:
            try:
                box["result"] = tool.execute(arguments)
            except Exception as error:  # падение инструмента — данные для LLM, не крах
                logger.warning("Инструмент %s упал: %s", name, error, exc_info=True)
                box["result"] = ToolResult(
                    ok=False, error=f"инструмент завершился ошибкой: {error}"
                )

        worker = threading.Thread(target=_run, name=f"tool-{name}", daemon=True)
        worker.start()
        worker.join(timeout_s)
        if worker.is_alive():
            logger.warning("Инструмент %s превысил таймаут %.1f с", name, timeout_s)
            return ToolResult(ok=False, error=f"превышен таймаут {timeout_s:.1f} с")
        return box.get("result", ToolResult(ok=False, error="инструмент не вернул результат"))