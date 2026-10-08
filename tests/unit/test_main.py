"""Тесты логики точки входа (QApplication создаёт только pytest-qt)."""

from __future__ import annotations

import pytest
from PySide6.QtCore import QObject
from pytestqt.qtbot import QtBot

from microchel.animation.queue import Priority
from microchel.character.states import CharacterState
from microchel.desktop.main import (
    parse_args,
    select_qt_platform,
    start_showcase,
    states_with_clips,
)

EMPTY_ENV: dict[str, str] = {}


def test_wayland_session_selects_xcb() -> None:
    env = {"XDG_SESSION_TYPE": "wayland"}
    assert select_qt_platform(env) == "xcb"


def test_wayland_display_without_session_type() -> None:
    env = {"WAYLAND_DISPLAY": "wayland-0"}
    assert select_qt_platform(env) == "xcb"


def test_x11_session_keeps_default() -> None:
    env = {"XDG_SESSION_TYPE": "x11"}
    assert select_qt_platform(env) is None


def test_explicit_qt_platform_not_overridden() -> None:
    env = {"XDG_SESSION_TYPE": "wayland", "QT_QPA_PLATFORM": "offscreen"}
    assert select_qt_platform(env) is None


def test_empty_env_keeps_default() -> None:
    assert select_qt_platform(EMPTY_ENV) is None


def test_parse_args_flags() -> None:
    args = parse_args([])
    assert args.demo is False
    assert args.showcase is False
    assert args.demo_events is False
    args = parse_args(["--demo", "--demo-events"])
    assert args.demo is True
    assert args.demo_events is True


def test_states_with_clips_keeps_states_with_prefixes() -> None:
    available = states_with_clips(["Idle/Happy", "Walk/Normal", "Sleep/Calm"])
    assert available == {CharacterState.IDLE, CharacterState.WALK, CharacterState.SLEEP}


def test_states_with_clips_empty_input() -> None:
    # пусто — FSM добавит IDLE сам; поведение без клипов не включается (NF-P3.5)
    assert states_with_clips([]) == set()


def test_parse_args_showcase_flag() -> None:
    args = parse_args(["--showcase"])
    assert args.showcase is True
    assert args.demo is False


def test_parse_args_demo_and_showcase_mutually_exclusive() -> None:
    with pytest.raises(SystemExit):
        parse_args(["--demo", "--showcase"])


def test_start_showcase_plays_all_clips_in_order(qtbot: QtBot) -> None:
    """Idle первым, далее по алфавиту; каждый слот — restart+loop, затем новый цикл."""
    calls: list[tuple[str, Priority, bool | int, bool]] = []

    class FakeWindow(QObject):
        def available_clip_names(self) -> list[str]:
            return ["Walk/Normal", "Idle/Happy", "Blink/Happy"]

        def play_clip(
            self,
            name: str,
            *,
            priority: Priority = Priority.BEHAVIOR,
            loop: bool | int = True,
            restart: bool = False,
        ) -> bool:
            calls.append((name, priority, loop, restart))
            return True

    timer = start_showcase(FakeWindow(), seconds=0.05)
    qtbot.waitUntil(lambda: len(calls) >= 4, timeout=3000)
    timer.stop()
    names = [call[0] for call in calls]
    assert names == ["Idle/Happy", "Blink/Happy", "Walk/Normal", "Idle/Happy"]
    _first_name, first_priority, first_loop, first_restart = calls[0]
    assert first_priority is Priority.IDLE
    assert first_loop is True
    assert first_restart is True


def test_start_showcase_without_clips_timer_inactive() -> None:
    class EmptyWindow(QObject):
        def available_clip_names(self) -> list[str]:
            return []

        def play_clip(self, *_args: object, **_kwargs: object) -> bool:
            return False

    timer = start_showcase(EmptyWindow())
    assert not timer.isActive()
