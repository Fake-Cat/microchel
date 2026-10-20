"""Типы Agent Core (PHASE 5): задачи, лимиты, шаги, статусы, сообщения LLM.

Чистые frozen dataclass без Qt и сети — юнит-тестируются изолированно.
Схема по docs/PHASE5_PLAN.md и ARCHITECTURE.md.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


class TaskStatus(StrEnum):
    """Итоговый статус выполнения задачи агентом."""

    COMPLETED = "completed"  # LLM сформировал финальный ответ
    FAILED = "failed"  # ошибка LLM/инфраструктуры (инструменты не рушат задачу)
    CANCELLED = "cancelled"  # отмена пользователем (Ctrl+C / cancel())
    LIMIT_REACHED = "limit_reached"  # исчерпан один из лимитов Limits


@dataclass(frozen=True, slots=True)
class Limits:
    """Бюджеты одной задачи: шаги, вызовы LLM/инструментов, время."""

    max_steps: int = 8
    max_llm_calls: int = 12
    max_tool_calls: int = 24
    wall_time_s: float = 180.0
    llm_timeout_s: float = 60.0
    tool_timeout_s: float = 15.0
    max_tool_output_chars: int = 8000


@dataclass(frozen=True, slots=True)
class ToolCall:
    """Запрос вызова инструмента от LLM."""

    id: str
    name: str
    arguments: dict[str, Any]
    signature: str = ""  # провайдерская подпись витка (Gemini thoughtSignature)


@dataclass(frozen=True, slots=True)
class ToolCallResult:
    """Результат вызова инструмента (для истории и журнала)."""

    id: str
    name: str
    ok: bool
    data: Any = None
    error: str = ""


@dataclass(frozen=True, slots=True)
class LLMMessage:
    """Сообщение истории диалога с LLM (унифицированный формат адаптеров)."""

    role: str  # "system" | "user" | "assistant" | "tool"
    content: str = ""
    tool_calls: tuple[ToolCall, ...] = ()
    tool_call_id: str = ""  # для роли "tool"
    name: str = ""  # для роли "tool" — имя инструмента


@dataclass(frozen=True, slots=True)
class LLMResponse:
    """Ответ LLM: текст и/или запросы вызова инструментов."""

    text: str
    tool_calls: tuple[ToolCall, ...] = ()
    finish_reason: str = ""
    model: str = ""


@dataclass(frozen=True, slots=True)
class StepRecord:
    """Один шаг исполнителя: текст LLM и результаты вызванных инструментов."""

    step: int
    llm_text: str
    tool_calls: tuple[ToolCallResult, ...] = ()
    error: str = ""


@dataclass(frozen=True, slots=True)
class TaskSpec:
    """Входная задача: поручение пользователя + бюджет."""

    prompt: str
    task_id: str = field(default_factory=lambda: uuid.uuid4().hex)
    limits: Limits = field(default_factory=Limits)


@dataclass(frozen=True, slots=True)
class TaskResult:
    """Итог задачи: статус, ответ, шаги и счётчики для журнала/CLI."""

    task_id: str
    status: TaskStatus
    answer: str
    steps: tuple[StepRecord, ...] = ()
    llm_calls: int = 0
    tool_calls: int = 0
    elapsed_s: float = 0.0
    error: str = ""