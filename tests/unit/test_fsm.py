"""Юнит-тесты FSM поведения (PHASE 3, FR-P3.1, FR-P3.2, FR-P3.5)."""

from __future__ import annotations

import random
from dataclasses import replace

from microchel.character.config import BehaviorConfig
from microchel.character.fsm import BehaviorFSM, is_night
from microchel.character.states import CharacterState
from microchel.common.events import UserEventKind

SEED = 42


def make_fsm(
    config: BehaviorConfig | None = None,
    *,
    available: set[CharacterState] | None = None,
    hour: int = 12,
) -> BehaviorFSM:
    return BehaviorFSM(
        config or BehaviorConfig(),
        rng=random.Random(SEED),
        available=available,
        hour=lambda: hour,
    )


class TestIsNight:
    def test_wrap_interval(self) -> None:
        # night_from=23, night_to=8 — переход через полночь
        assert is_night(23, 23, 8)
        assert is_night(2, 23, 8)
        assert is_night(7, 23, 8)
        assert not is_night(8, 23, 8)
        assert not is_night(12, 23, 8)
        assert not is_night(22, 23, 8)

    def test_same_hours_means_never(self) -> None:
        assert not is_night(5, 8, 8)

    def test_straight_interval(self) -> None:
        assert is_night(10, 8, 23)
        assert not is_night(5, 8, 23)


class TestFSMBasics:
    def test_starts_idle(self) -> None:
        assert make_fsm().state is CharacterState.IDLE

    def test_idle_always_available_even_if_excluded(self) -> None:
        fsm = make_fsm(available={CharacterState.WALK})
        assert CharacterState.IDLE in fsm.available

    def test_available_respected(self) -> None:
        fsm = make_fsm(available={CharacterState.IDLE, CharacterState.SIT})
        assert fsm.available == {CharacterState.IDLE, CharacterState.SIT}

    def test_state_duration_within_pair(self) -> None:
        fsm = make_fsm()
        for state in CharacterState:
            fsm.force(state)
            low, high = fsm.config.duration_ms(state)
            assert low <= fsm.state_duration_ms() <= high


class TestTimeoutTransitions:
    def test_transient_returns_to_idle(self) -> None:
        fsm = make_fsm()
        for state in sorted(set(CharacterState) - {CharacterState.IDLE}, key=str):
            fsm.force(state)
            assert fsm.on_timeout() is CharacterState.IDLE

    def test_idle_picks_transient_state(self) -> None:
        fsm = make_fsm()
        seen: set[CharacterState] = set()
        for _ in range(400):
            fsm.force(CharacterState.IDLE)
            next_state = fsm.on_timeout()
            assert next_state is not CharacterState.IDLE
            seen.add(next_state)
        # при seed все одноразовые состояния достижимы
        assert seen == set(CharacterState) - {CharacterState.IDLE}

    def test_unavailable_states_never_chosen(self) -> None:
        fsm = make_fsm(available={CharacterState.IDLE, CharacterState.WALK})
        for _ in range(100):
            fsm.force(CharacterState.IDLE)
            assert fsm.on_timeout() is CharacterState.WALK

    def test_all_weights_zero_stays_idle(self) -> None:
        config = replace(
            BehaviorConfig(),
            weight_walk=0,
            weight_sit=0,
            weight_coffee=0,
            weight_thinking=0,
            weight_sleep=0,
        )
        fsm = make_fsm(config)
        assert fsm.on_timeout() is CharacterState.IDLE


class TestNightDominance:
    def test_night_sleep_dominates(self) -> None:
        fsm = make_fsm(hour=2)  # ночь: 23..8
        sleep_count = 0
        total = 500
        for _ in range(total):
            fsm.force(CharacterState.IDLE)
            if fsm.on_timeout() is CharacterState.SLEEP:
                sleep_count += 1
        assert sleep_count / total > 0.65

    def test_day_sleep_rare(self) -> None:
        fsm = make_fsm(hour=12)
        sleep_count = 0
        total = 500
        for _ in range(total):
            fsm.force(CharacterState.IDLE)
            if fsm.on_timeout() is CharacterState.SLEEP:
                sleep_count += 1
        assert sleep_count / total < 0.25


class TestUserEvents:
    def test_drag_interrupts_walk(self) -> None:
        fsm = make_fsm()
        fsm.force(CharacterState.WALK)
        assert fsm.on_user_event(UserEventKind.DRAG_START) is CharacterState.IDLE
        assert fsm.state is CharacterState.IDLE

    def test_drag_does_not_interrupt_other_states(self) -> None:
        fsm = make_fsm()
        others = set(CharacterState) - {CharacterState.IDLE, CharacterState.WALK}
        for state in sorted(others, key=str):
            fsm.force(state)
            assert fsm.on_user_event(UserEventKind.DRAG_START) is None
            assert fsm.state is state

    def test_click_never_changes_state(self) -> None:
        fsm = make_fsm()
        fsm.force(CharacterState.WALK)
        assert fsm.on_user_event(UserEventKind.CLICK) is None
        assert fsm.state is CharacterState.WALK

    def test_drag_end_is_noop(self) -> None:
        fsm = make_fsm()
        fsm.force(CharacterState.WALK)
        assert fsm.on_user_event(UserEventKind.DRAG_END) is None
        assert fsm.state is CharacterState.WALK
