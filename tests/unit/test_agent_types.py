"""Тесты типов Agent Core: статусы, лимиты, спецификации задач."""

from dataclasses import FrozenInstanceError

import pytest

from microchel.agent.types import (
    Limits,
    LLMMessage,
    LLMResponse,
    StepRecord,
    TaskResult,
    TaskSpec,
    TaskStatus,
    ToolCall,
    ToolCallResult,
)


def test_task_status_values() -> None:
    assert TaskStatus.COMPLETED.value == "completed"
    assert TaskStatus.FAILED.value == "failed"
    assert TaskStatus.CANCELLED.value == "cancelled"
    assert TaskStatus.LIMIT_REACHED.value == "limit_reached"


def test_limits_defaults() -> None:
    limits = Limits()
    assert limits.max_steps == 8
    assert limits.max_llm_calls == 12
    assert limits.max_tool_calls == 24
    assert limits.wall_time_s == 180.0
    assert limits.max_tool_output_chars == 8000


def test_task_spec_generates_unique_ids() -> None:
    first = TaskSpec(prompt="привет")
    second = TaskSpec(prompt="привет")
    assert first.task_id
    assert first.task_id != second.task_id


def test_frozen_types_reject_mutation() -> None:
    call = ToolCall(id="c0", name="system.metrics", arguments={})
    with pytest.raises(FrozenInstanceError):
        call.name = "other"  # type: ignore[misc]


def test_llm_message_defaults() -> None:
    message = LLMMessage(role="user", content="hi")
    assert message.tool_calls == ()
    assert message.tool_call_id == ""
    assert message.name == ""


def test_task_result_holds_steps() -> None:
    step = StepRecord(
        step=1, llm_text="текст", tool_calls=(ToolCallResult(id="c0", name="t", ok=True),)
    )
    result = TaskResult(
        task_id="t1", status=TaskStatus.COMPLETED, answer="ок", steps=(step,), llm_calls=1
    )
    assert result.steps[0].tool_calls[0].ok
    assert result.llm_calls == 1
    assert LLMResponse(text="").tool_calls == ()