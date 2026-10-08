"""Юнит-тесты состояний персонажа (PHASE 3, FR-P3.1)."""

from __future__ import annotations

from microchel.animation.queue import Priority
from microchel.character.states import (
    STATE_CLIP_PREFIX,
    STATE_PRIORITY,
    TRANSIENT_STATES,
    CharacterState,
    clip_prefix_for,
)


class TestCharacterState:
    def test_six_states(self) -> None:
        assert set(CharacterState) == {
            CharacterState.IDLE,
            CharacterState.WALK,
            CharacterState.SLEEP,
            CharacterState.SIT,
            CharacterState.COFFEE,
            CharacterState.THINKING,
        }

    def test_values_lowercase(self) -> None:
        assert CharacterState.WALK.value == "walk"
        assert CharacterState.SLEEP.value == "sleep"

    def test_every_state_has_clip_prefix(self) -> None:
        assert set(STATE_CLIP_PREFIX) == set(CharacterState)
        for state, prefix in STATE_CLIP_PREFIX.items():
            assert prefix, f"пустой префикс клипа для {state}"

    def test_clip_prefix_for(self) -> None:
        assert clip_prefix_for(CharacterState.COFFEE) == "Coffee"
        assert clip_prefix_for(CharacterState.IDLE) == "Idle"

    def test_idle_priority_is_idle_others_behavior(self) -> None:
        assert STATE_PRIORITY[CharacterState.IDLE] is Priority.IDLE
        for state in CharacterState:
            if state is CharacterState.IDLE:
                continue
            assert STATE_PRIORITY[state] is Priority.BEHAVIOR

    def test_transient_states_exclude_idle(self) -> None:
        assert CharacterState.IDLE not in TRANSIENT_STATES
        assert frozenset(CharacterState) - {CharacterState.IDLE} == TRANSIENT_STATES
