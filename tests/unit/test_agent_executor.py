"""Тесты AgentExecutor: цикл LLM↔инструменты, лимиты, отмена, события, журнал."""

from pathlib import Path
from typing import Any

from microchel.agent.executor import AgentExecutor
from microchel.agent.journal import ExecutionJournal
from microchel.agent.llm.base import LLMNetworkError
from microchel.agent.llm.fake import FakeProvider
from microchel.agent.types import Limits, LLMResponse, TaskSpec, TaskStatus, ToolCall
from microchel.common.event_bus import EventBus
from microchel.common.events import AgentTaskFinished, AgentTaskStarted, UserPrompt
from microchel.tools import build_default_registry
from microchel.tools.base import ToolResult, ToolSpec
from microchel.tools.registry import ToolRegistry


class _Clock:
    def __init__(self) -> None:
        self.t = 0.0

    def __call__(self) -> float:
        return self.t


class _RaisingProvider:
    name = "raising"

    def complete(self, messages: Any, tools: Any) -> LLMResponse:
        raise LLMNetworkError("сеть недоступна")


class _BigDataTool:
    def spec(self) -> ToolSpec:
        return ToolSpec(
            name="big",
            description="большие данные",
            parameters={"type": "object", "properties": {}},
        )

    def execute(self, arguments: dict[str, Any]) -> ToolResult:  # noqa: ARG002
        return ToolResult(ok=True, data={"text": "х" * 10000})


def test_happy_path_tool_call_then_answer() -> None:
    provider = FakeProvider(
        responses=[
            LLMResponse(
                text="", tool_calls=(ToolCall(id="c0", name="system.metrics", arguments={}),)
            ),
            LLMResponse(text="Компьютер в порядке."),
        ]
    )
    executor = AgentExecutor(provider, build_default_registry())
    result = executor.run(TaskSpec(prompt="Проверь состояние компьютера"))
    assert result.status is TaskStatus.COMPLETED
    assert result.answer == "Компьютер в порядке."
    assert result.llm_calls == 2
    assert result.tool_calls == 1
    assert len(result.steps) == 2
    assert result.steps[0].tool_calls[0].ok
    cpu_count = result.steps[0].tool_calls[0].data["cpu_count"]
    assert cpu_count is None or cpu_count >= 1


def test_tool_error_does_not_fail_task() -> None:
    provider = FakeProvider(
        responses=[
            LLMResponse(text="", tool_calls=(ToolCall(id="c0", name="нет_такого", arguments={}),)),
            LLMResponse(text="Инструмент недоступен, отвечаю по-другому."),
        ]
    )
    executor = AgentExecutor(provider, build_default_registry())
    result = executor.run(TaskSpec(prompt="задача"))
    assert result.status is TaskStatus.COMPLETED
    assert not result.steps[0].tool_calls[0].ok
    assert "неизвестный" in result.steps[0].tool_calls[0].error


def test_max_steps_limit() -> None:
    endless = FakeProvider(
        responses=[
            LLMResponse(
                text="", tool_calls=(ToolCall(id=f"c{i}", name="system.metrics", arguments={}),)
            )
            for i in range(10)
        ]
    )
    executor = AgentExecutor(endless, build_default_registry())
    result = executor.run(TaskSpec(prompt="бесконечно", limits=Limits(max_steps=2)))
    assert result.status is TaskStatus.LIMIT_REACHED
    assert result.llm_calls == 2
    assert "бюджет" in result.error


def test_llm_error_marks_failed() -> None:
    executor = AgentExecutor(_RaisingProvider(), build_default_registry())
    result = executor.run(TaskSpec(prompt="задача"))
    assert result.status is TaskStatus.FAILED
    assert "сеть недоступна" in result.error


def test_cancel_during_run() -> None:
    executor_ref: dict[str, AgentExecutor] = {}

    class _CancelProvider:
        name = "cancel"

        def complete(self, messages: Any, tools: Any) -> LLMResponse:
            executor_ref["e"].cancel()
            return LLMResponse(
                text="", tool_calls=(ToolCall(id="c0", name="system.metrics", arguments={}),)
            )

    executor = AgentExecutor(_CancelProvider(), build_default_registry())
    executor_ref["e"] = executor
    result = executor.run(TaskSpec(prompt="задача"))
    assert result.status is TaskStatus.CANCELLED


def test_wall_time_limit_with_fake_clock() -> None:
    clock = _Clock()

    class _SlowProvider(FakeProvider):
        def complete(self, messages: Any, tools: Any) -> LLMResponse:
            clock.t += 100.0
            return LLMResponse(
                text="", tool_calls=(ToolCall(id="c0", name="system.metrics", arguments={}),)
            )

    executor = AgentExecutor(_SlowProvider(), build_default_registry(), clock=clock)
    result = executor.run(TaskSpec(prompt="долго", limits=Limits(max_steps=50, wall_time_s=50.0)))
    assert result.status is TaskStatus.LIMIT_REACHED
    assert "времени" in result.error


def test_events_and_journal_flow(tmp_path: Path) -> None:
    bus = EventBus()
    received: list[object] = []
    bus.subscribe(UserPrompt, lambda event: received.append(event))
    bus.subscribe(AgentTaskStarted, lambda event: received.append(event))
    bus.subscribe(AgentTaskFinished, lambda event: received.append(event))
    journal = ExecutionJournal(tmp_path / "journal.jsonl")
    provider = FakeProvider(responses=[LLMResponse(text="ок")])
    executor = AgentExecutor(provider, build_default_registry(), events=bus, journal=journal)
    executor.run(TaskSpec(prompt="привет", task_id="t-test"))
    assert [type(event).__name__ for event in received] == [
        "UserPrompt",
        "AgentTaskStarted",
        "AgentTaskFinished",
    ]
    assert received[-1].status == "completed"  # type: ignore[attr-defined]
    events = [entry.event for entry in journal.entries()]
    assert events == ["task_started", "llm_call", "task_finished"]
    lines = (tmp_path / "journal.jsonl").read_text(encoding="utf-8").splitlines()
    assert len(lines) == 3


def test_tool_output_truncated_for_llm() -> None:
    registry = ToolRegistry()
    registry.register(_BigDataTool())
    provider = FakeProvider(
        responses=[
            LLMResponse(text="", tool_calls=(ToolCall(id="c0", name="big", arguments={}),)),
            LLMResponse(text="хватит"),
        ]
    )
    executor = AgentExecutor(provider, registry)
    executor.run(TaskSpec(prompt="дай данные", limits=Limits(max_tool_output_chars=50)))
    second_call_messages = provider.calls[1][0]
    tool_message = next(m for m in second_call_messages if m.role == "tool")
    assert len(tool_message.content) == 50


def test_budget_of_tool_calls() -> None:
    provider = FakeProvider(
        responses=[
            LLMResponse(
                text="",
                tool_calls=(
                    ToolCall(id="c0", name="system.metrics", arguments={}),
                    ToolCall(id="c1", name="system.metrics", arguments={}),
                ),
            ),
            LLMResponse(text="готово"),
        ]
    )
    executor = AgentExecutor(provider, build_default_registry())
    result = executor.run(TaskSpec(prompt="задача", limits=Limits(max_tool_calls=1)))
    assert result.tool_calls == 1
    assert not result.steps[0].tool_calls[1].ok
    assert "бюджет" in result.steps[0].tool_calls[1].error


def test_tool_messages_use_expected_roles() -> None:
    provider = FakeProvider(
        responses=[
            LLMResponse(
                text="", tool_calls=(ToolCall(id="c0", name="system.metrics", arguments={}),)
            ),
            LLMResponse(text="ок"),
        ]
    )
    executor = AgentExecutor(provider, build_default_registry())
    executor.run(TaskSpec(prompt="задача"))
    messages = provider.calls[1][0]
    assert [m.role for m in messages] == ["system", "user", "assistant", "tool"]
    assert messages[-1].name == "system.metrics"
    assert messages[-1].tool_call_id == "c0"