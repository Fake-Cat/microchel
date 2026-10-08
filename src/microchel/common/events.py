"""Типы событий (PHASE 3, FR-P3.7): пользователь, система, действие персонажа.

Схема по ARCHITECTURE.md («Форматы событий», уточнена в PHASE 3).
Чистые frozen dataclass без Qt — тестируются юнит-тестами.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class UserEventKind(StrEnum):
    """Что сделал пользователь с персонажем."""

    CLICK = "click"  # быстрый ЛКМ без смещения
    DRAG_START = "drag_start"  # начало перетаскивания (сдвиг ≥ порога)
    DRAG_END = "drag_end"  # отпускание после перетаскивания


class SystemEventKind(StrEnum):
    """Системные события (до PHASE 7 — только синтетический источник)."""

    SYNTHETIC = "synthetic"  # демонстрационный тик для проверки механики


@dataclass(frozen=True, slots=True)
class UserEvent:
    """Событие взаимодействия пользователя (desktop → character)."""

    kind: UserEventKind


@dataclass(frozen=True, slots=True)
class SystemEvent:
    """Системное событие (monitoring → character; PHASE 7 — реальные источники)."""

    kind: SystemEventKind
    payload: str = ""


@dataclass(frozen=True, slots=True)
class CharacterAction:
    """Действие FSM, объявленное наружу (character → agent, PHASE 5+)."""

    action: str  # имя состояния: walk, sleep, coffee, ...
