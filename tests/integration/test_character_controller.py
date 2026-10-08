"""Интеграционные тесты контроллера поведения (pytest-qt, PHASE 3).

Колбэки play/move — заглушки-регистраторы: таймеры реально тикают в Qt
event loop, событийная шина настоящая. NF-P3.1.
"""

from __future__ import annotations

import random
from collections.abc import Iterator
from dataclasses import replace

import pytest
from pytestqt.qtbot import QtBot

from microchel.animation.queue import Priority
from microchel.character.config import BehaviorConfig
from microchel.character.controller import CharacterController
from microchel.character.fsm import BehaviorFSM
from microchel.character.states import CharacterState
from microchel.common.event_bus import EventBus
from microchel.common.events import (
    CharacterAction,
    SystemEvent,
    SystemEventKind,
    UserEvent,
    UserEventKind,
)


def fast_config() -> BehaviorConfig:
    """Короткие тайминги; достигим только WALK (вес 1, остальные 0), день."""
    return replace(
        BehaviorConfig(),
        idle_min_ms=150,
        idle_max_ms=250,
        walk_min_ms=300,
        walk_max_ms=500,
        weight_sit=0,
        weight_coffee=0,
        weight_thinking=0,
        weight_sleep=0,
        weight_walk=1,
        walk_interval_ms=10,
        walk_step_px=3,
    )


def make_fsm(config: BehaviorConfig) -> BehaviorFSM:
    return BehaviorFSM(config, rng=random.Random(3), hour=lambda: 12)


class Recorder:
    """Заглушки play/move: записывают вызовы, отдают управимый результат."""

    def __init__(self) -> None:
        self.plays: list[tuple[str, Priority, bool | int, bool]] = []
        self.moves: list[int] = []
        self.move_ok = True
        self.play_ok = True

    def play(self, prefix: str, priority: Priority, loop: bool | int, restart: bool) -> bool:
        self.plays.append((prefix, priority, loop, restart))
        return self.play_ok

    def move_by(self, dx: int) -> bool:
        self.moves.append(dx)
        return self.move_ok


@pytest.fixture
def bus() -> EventBus:
    return EventBus()


@pytest.fixture
def recorder() -> Recorder:
    return Recorder()


@pytest.fixture
def controller(bus: EventBus, recorder: Recorder) -> Iterator[CharacterController]:
    ctl = CharacterController(
        make_fsm(fast_config()), bus, play=recorder.play, move_by=recorder.move_by
    )
    yield ctl
    ctl.stop()


class TestLifecycle:
    def test_start_plays_idle_and_emits_action(
        self, bus: EventBus, recorder: Recorder, controller: CharacterController
    ) -> None:
        actions: list[str] = []
        bus.subscribe(CharacterAction, lambda e: actions.append(e.action))
        controller.start()
        assert controller.started
        assert recorder.plays == [("Idle", Priority.IDLE, True, True)]
        assert actions == ["idle"]

    def test_start_twice_is_noop(self, recorder: Recorder, controller: CharacterController) -> None:
        controller.start()
        controller.start()
        assert len(recorder.plays) == 1

    def test_missing_clip_does_not_crash(
        self, recorder: Recorder, controller: CharacterController
    ) -> None:
        recorder.play_ok = False
        controller.start()
        assert controller.started  # поведение живёт без анимаций (FR-P3.1)

    def test_stop_stops_timers_and_unsubscribes(
        self, bus: EventBus, recorder: Recorder, controller: CharacterController
    ) -> None:
        controller.start()
        controller.stop()
        assert not controller.started
        assert not controller._state_timer.isActive()
        assert not controller._walk_timer.isActive()
        count = len(recorder.plays)
        bus.emit(UserEvent(UserEventKind.CLICK))
        assert len(recorder.plays) == count  # подписки сняты


class TestTransitions:
    def test_timeout_reaches_walk_and_moves(
        self, qtbot: QtBot, bus: EventBus, recorder: Recorder, controller: CharacterController
    ) -> None:
        actions: list[str] = []
        bus.subscribe(CharacterAction, lambda e: actions.append(e.action))
        controller.start()
        qtbot.waitUntil(lambda: controller.fsm.state is CharacterState.WALK, timeout=2000)
        assert "Walk" in [p[0] for p in recorder.plays]
        assert "walk" in actions
        qtbot.waitUntil(lambda: len(recorder.moves) >= 3, timeout=2000)
        assert all(dx == 3 for dx in recorder.moves)  # направление не менялось

    def test_walk_reverses_at_edge(
        self, qtbot: QtBot, recorder: Recorder, controller: CharacterController
    ) -> None:
        recorder.move_ok = False  # композитор не двигает окно → край
        controller.start()
        qtbot.waitUntil(lambda: len(recorder.moves) >= 2, timeout=2000)
        assert recorder.moves[0] > 0
        assert recorder.moves[1] < 0  # разворот после упора (FR-P3.4)

    def test_walk_timer_stopped_outside_walk(
        self, qtbot: QtBot, controller: CharacterController
    ) -> None:
        controller.start()
        qtbot.waitUntil(lambda: controller.fsm.state is not CharacterState.WALK, timeout=2000)
        assert not controller._walk_timer.isActive()


class TestUserEvents:
    def test_click_plays_reaction_state_unchanged(
        self, bus: EventBus, recorder: Recorder, controller: CharacterController
    ) -> None:
        controller.start()
        state_before = controller.fsm.state
        bus.emit(UserEvent(UserEventKind.CLICK))
        assert recorder.plays[-1] == ("Blink", Priority.REACTION, False, False)
        assert controller.reaction_active
        assert controller.fsm.state is state_before

    def test_double_click_not_stacked(
        self, bus: EventBus, recorder: Recorder, controller: CharacterController
    ) -> None:
        controller.start()
        bus.emit(UserEvent(UserEventKind.CLICK))
        count = len(recorder.plays)
        bus.emit(UserEvent(UserEventKind.CLICK))
        assert len(recorder.plays) == count

    def test_reaction_finish_resumes_state(
        self, bus: EventBus, recorder: Recorder, controller: CharacterController
    ) -> None:
        controller.start()
        bus.emit(UserEvent(UserEventKind.CLICK))
        count = len(recorder.plays)
        controller.notify_animation_finished("Blink/State")
        assert not controller.reaction_active
        assert len(recorder.plays) == count + 1
        assert recorder.plays[-1] == ("Idle", Priority.IDLE, True, True)

    def test_state_change_during_reaction_defers_clip(
        self, qtbot: QtBot, bus: EventBus, recorder: Recorder, controller: CharacterController
    ) -> None:
        controller.start()
        bus.emit(UserEvent(UserEventKind.CLICK))
        count = len(recorder.plays)
        qtbot.waitUntil(lambda: controller.fsm.state is CharacterState.WALK, timeout=2000)
        assert len(recorder.plays) == count  # клип состояния отложен (FR-P3.5)
        controller.notify_animation_finished("Blink/State")
        assert recorder.plays[-1] == ("Walk", Priority.BEHAVIOR, True, True)

    def test_drag_interrupts_walk(
        self, qtbot: QtBot, bus: EventBus, recorder: Recorder, controller: CharacterController
    ) -> None:
        controller.start()
        qtbot.waitUntil(lambda: controller.fsm.state is CharacterState.WALK, timeout=2000)
        qtbot.waitUntil(lambda: len(recorder.moves) >= 2, timeout=2000)
        bus.emit(UserEvent(UserEventKind.DRAG_START))
        assert controller.fsm.state is CharacterState.IDLE
        assert recorder.plays[-1] == ("Idle", Priority.IDLE, True, True)
        count = len(recorder.moves)
        qtbot.wait(60)  # меньше idle-паузы (150 мс) — новый walk ещё не начался
        assert len(recorder.moves) == count  # walk-таймер остановлен


class TestSystemEvents:
    def test_system_event_plays_with_event_priority(
        self, bus: EventBus, recorder: Recorder, controller: CharacterController
    ) -> None:
        actions: list[str] = []
        bus.subscribe(CharacterAction, lambda e: actions.append(e.action))
        controller.start()
        bus.emit(SystemEvent(SystemEventKind.SYNTHETIC, "тест"))
        assert recorder.plays[-1] == ("Blink", Priority.EVENT, False, False)
        assert actions == ["idle"]  # состояние не изменилось (FR-P3.6)
        assert not controller.reaction_active  # EVENT ≠ реакция на клик

    def test_system_event_after_click_requests_both(
        self, bus: EventBus, recorder: Recorder, controller: CharacterController
    ) -> None:
        controller.start()
        bus.emit(UserEvent(UserEventKind.CLICK))
        bus.emit(SystemEvent(SystemEventKind.SYNTHETIC))
        # очередь плеера сама разрулит приоритеты (REACTION > EVENT) — здесь видим оба запроса
        assert recorder.plays[-2:] == [
            ("Blink", Priority.REACTION, False, False),
            ("Blink", Priority.EVENT, False, False),
        ]
        assert controller.reaction_active

