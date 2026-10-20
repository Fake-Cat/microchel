"""Исполнитель задач агента (PHASE 5): цикл LLM ↔ инструменты с лимитами.

Один вызов LLM → при tool calls инструменты выполняются синхронно, их
результаты (обрезанные как недоверенные) возвращаются в историю → повтор.
Ошибки инструментов не рушат задачу; ошибка LLM — статус FAILED. Все лимиты
проверяются на каждой итерации. События шлются в common.event_bus, ход
выполнения пишется в ExecutionJournal.
"""

from __future__ import annotations

import json
import logging
import threading
import time
from collections.abc import Callable

from microchel.agent.journal import ExecutionJournal, JournalEntry
from microchel.agent.llm.base import LLMError, LLMProvider
from microchel.agent.prompt import SYSTEM_PROMPT
from microchel.agent.types import (
    Limits,
    LLMMessage,
    StepRecord,
    TaskResult,
    TaskSpec,
    TaskStatus,
    ToolCallResult,
)
from microchel.common.event_bus import EventBus
from microchel.common.events import AgentTaskFinished, AgentTaskStarted, UserPrompt
from microchel.tools.registry import ToolRegistry

logger = logging.getLogger(__name__)


class AgentExecutor:
    """Цикл агента: LLM → инструменты → LLM → ответ, с бюджетами и журналом."""

    def __init__(
        self,
        provider: LLMProvider,
        registry: ToolRegistry,
        *,
        events: EventBus | None = None,
        journal: ExecutionJournal | None = None,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._provider = provider
        self._registry = registry
        self._events = events
        self._journal = journal
        self._clock = clock
        self._cancel = threading.Event()

    def cancel(self) -> None:
        """Мягкая отмена текущей задачи (Ctrl+C / кнопка Stop в GUI)."""
        self._cancel.set()

    def run(self, spec: TaskSpec) -> TaskResult:
        """Выполнить задачу; всегда возвращает TaskResult, исключения не уходят наружу."""
        self._cancel.clear()
        limits = spec.limits
        started = self._clock()
        self._emit(UserPrompt(spec.prompt))
        self._emit(AgentTaskStarted(spec.task_id))
        self._record(spec.task_id, "task_started", {"prompt": spec.prompt})

        messages: list[LLMMessage] = [
            LLMMessage(role="system", content=SYSTEM_PROMPT),
            LLMMessage(role="user", content=spec.prompt),
        ]
        steps: list[StepRecord] = []
        llm_calls = 0
        tool_calls_count = 0
        status = TaskStatus.LIMIT_REACHED
        answer = ""
        error = ""

        while True:
            if self._cancel.is_set():
                status = TaskStatus.CANCELLED
                break
            if self._clock() - started >= limits.wall_time_s:
                error = f"превышен лимит времени {limits.wall_time_s:.0f} с"
                break
            if len(steps) >= limits.max_steps or llm_calls >= limits.max_llm_calls:
                error = "исчерпан бюджет шагов/вызовов LLM"
                break

            llm_calls += 1
            try:
                response = self._provider.complete(messages, self._registry.specs())
            except LLMError as exc:
                logger.error("Ошибка LLM: %s", exc)
                status = TaskStatus.FAILED
                error = f"ошибка LLM: {exc}"
                break
            self._record(
                spec.task_id, "llm_call", {"n": llm_calls, "tool_calls": len(response.tool_calls)}
            )

            if not response.tool_calls:
                answer = response.text
                steps.append(StepRecord(step=len(steps) + 1, llm_text=response.text))
                status = TaskStatus.COMPLETED
                break

            messages.append(
                LLMMessage(role="assistant", content=response.text, tool_calls=response.tool_calls)
            )
            step_results: list[ToolCallResult] = []
            for call in response.tool_calls:
                if self._cancel.is_set():
                    break
                if tool_calls_count >= limits.max_tool_calls:
                    step_results.append(
                        ToolCallResult(
                            id=call.id,
                            name=call.name,
                            ok=False,
                            error="бюджет вызовов инструментов исчерпан",
                        )
                    )
                    continue
                tool_calls_count += 1
                result = self._registry.execute(
                    call.name, call.arguments, timeout_s=limits.tool_timeout_s
                )
                step_results.append(
                    ToolCallResult(
                        id=call.id,
                        name=call.name,
                        ok=result.ok,
                        data=result.data,
                        error=result.error,
                    )
                )
                self._record(
                    spec.task_id,
                    "tool_call",
                    {"name": call.name, "ok": result.ok, "error": result.error},
                )
                messages.append(
                    LLMMessage(
                        role="tool",
                        name=call.name,
                        tool_call_id=call.id,
                        content=_truncate(result, limits),
                    )
                )
            steps.append(
                StepRecord(
                    step=len(steps) + 1, llm_text=response.text, tool_calls=tuple(step_results)
                )
            )

        elapsed = self._clock() - started
        result = TaskResult(
            task_id=spec.task_id,
            status=status,
            answer=answer,
            steps=tuple(steps),
            llm_calls=llm_calls,
            tool_calls=tool_calls_count,
            elapsed_s=round(elapsed, 3),
            error=error,
        )
        self._record(spec.task_id, "task_finished", {"status": status.value, "error": error})
        self._emit(AgentTaskFinished(spec.task_id, status.value))
        return result

    def _emit(self, event: object) -> None:
        if self._events is None:
            return
        try:
            self._events.emit(event)
        except Exception:  # сбой подписчика не должен ронять задачу
            logger.warning("Сбой обработчика события %r", event, exc_info=True)

    def _record(self, task_id: str, event: str, data: dict) -> None:
        if self._journal is not None:
            self._journal.record(JournalEntry(task_id=task_id, event=event, data=data))


def _truncate(result: ToolCallResult, limits: Limits) -> str:
    """Вывод инструмента — недоверенные данные: обрезка по лимиту."""
    payload = json.dumps(
        {"ok": result.ok, "data": result.data, "error": result.error},
        ensure_ascii=False,
        default=str,
    )
    return payload[: limits.max_tool_output_chars]