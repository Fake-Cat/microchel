"""Состояния персонажа (PHASE 3, FR-P3.1) и их маппинг на анимации.

Чистые данные без Qt — тестируются юнит-тестами. Состояния поведения:
IDLE — базовое; WALK/SLEEP/SIT/COFFEE/THINKING — одноразовые, после
окончания возврат в IDLE. WAKE/эмоции — PHASE 4.
"""

from __future__ import annotations

from enum import StrEnum

from microchel.animation.queue import Priority


class CharacterState(StrEnum):
    """FSM-состояния персонажа (ARCHITECTURE.md, «Модель состояний»)."""

    IDLE = "idle"
    WALK = "walk"
    SLEEP = "sleep"
    SIT = "sit"
    COFFEE = "coffee"
    THINKING = "thinking"


# Префикс имени клипа плеера для каждого состояния (window.play_clip ищет по startswith)
STATE_CLIP_PREFIX: dict[CharacterState, str] = {
    CharacterState.IDLE: "Idle",
    CharacterState.WALK: "Walk",
    CharacterState.SLEEP: "Sleep",
    CharacterState.SIT: "Sit",
    CharacterState.COFFEE: "Coffee",
    CharacterState.THINKING: "Thinking",
}

# Приоритет анимации состояния: idle — IDLE, остальное — BEHAVIOR (ARCHITECTURE.md)
STATE_PRIORITY: dict[CharacterState, Priority] = {
    state: (Priority.IDLE if state is CharacterState.IDLE else Priority.BEHAVIOR)
    for state in CharacterState
}

# Одноразовые состояния (после — всегда возврат в IDLE); IDLE — базовое
TRANSIENT_STATES: frozenset[CharacterState] = frozenset(CharacterState) - {
    CharacterState.IDLE
}


def clip_prefix_for(state: CharacterState) -> str:
    """Префикс клипа состояния (деградация невозможна: маппинг полный)."""
    return STATE_CLIP_PREFIX[state]
