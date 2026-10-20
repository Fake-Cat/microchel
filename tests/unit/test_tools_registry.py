"""Тесты реестра инструментов: валидация аргументов, ошибки, таймауты."""

import time
from typing import Any

from microchel.tools.base import ToolResult, ToolSpec
from microchel.tools.registry import ToolRegistry


class _EchoTool:
    def spec(self) -> ToolSpec:
        return ToolSpec(
            name="echo",
            description="Эхо",
            parameters={
                "type": "object",
                "properties": {"text": {"type": "string"}, "count": {"type": "integer"}},
                "required": ["text"],
            },
        )

    def execute(self, arguments: dict[str, Any]) -> ToolResult:
        return ToolResult(ok=True, data={"echo": arguments["text"]})


class _BoomTool:
    def spec(self) -> ToolSpec:
        return ToolSpec(
            name="boom", description="Падает", parameters={"type": "object", "properties": {}}
        )

    def execute(self, arguments: dict[str, Any]) -> ToolResult:  # noqa: ARG002
        raise RuntimeError("я упал")


class _SlowTool:
    def spec(self) -> ToolSpec:
        return ToolSpec(
            name="slow", description="Медленный", parameters={"type": "object", "properties": {}}
        )

    def execute(self, arguments: dict[str, Any]) -> ToolResult:  # noqa: ARG002
        time.sleep(1.0)
        return ToolResult(ok=True)


def _registry_with(*tools: object) -> ToolRegistry:
    registry = ToolRegistry()
    for tool in tools:
        registry.register(tool)  # type: ignore[arg-type]
    return registry


def test_register_and_specs() -> None:
    registry = _registry_with(_EchoTool())
    assert registry.names() == ("echo",)
    assert registry.specs()[0].name == "echo"


def test_duplicate_name_rejected() -> None:
    registry = _registry_with(_EchoTool())
    try:
        registry.register(_EchoTool())
    except ValueError as error:
        assert "echo" in str(error)
    else:  # pragma: no cover
        raise AssertionError("ожидался ValueError")


def test_execute_success_and_unknown_tool() -> None:
    registry = _registry_with(_EchoTool())
    result = registry.execute("echo", {"text": "привет"})
    assert result.ok and result.data == {"echo": "привет"}
    unknown = registry.execute("нет_такого", {})
    assert not unknown.ok and "неизвестный" in unknown.error


def test_argument_validation() -> None:
    registry = _registry_with(_EchoTool())
    missing = registry.execute("echo", {})
    assert not missing.ok and "обязательного" in missing.error
    wrong_type = registry.execute("echo", {"text": 42})
    assert not wrong_type.ok and "ожидается тип string" in wrong_type.error
    unknown_arg = registry.execute("echo", {"text": "x", "лишнее": 1})
    assert not unknown_arg.ok and "неизвестный аргумент" in unknown_arg.error
    not_dict = registry.execute("echo", "строка")  # type: ignore[arg-type]
    assert not not_dict.ok and "JSON-объектом" in not_dict.error


def test_tool_exception_becomes_error_value() -> None:
    registry = _registry_with(_BoomTool())
    result = registry.execute("boom", {})
    assert not result.ok
    assert "я упал" in result.error


def test_tool_timeout_becomes_error_value() -> None:
    registry = _registry_with(_SlowTool())
    result = registry.execute("slow", {}, timeout_s=0.05)
    assert not result.ok
    assert "таймаут" in result.error