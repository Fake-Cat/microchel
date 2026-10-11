"""Тесты логики точки входа (QApplication создаёт только pytest-qt)."""

from __future__ import annotations

import logging

import pytest
from PySide6.QtCore import QObject, Qt
from pytestqt.qtbot import QtBot

from microchel.animation.queue import Priority
from microchel.animation.spec import ClipSpec
from microchel.character.states import CharacterState
from microchel.desktop.main import (
    invisible_platform_warning,
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


def test_invisible_platform_warning_offscreen() -> None:
    """offscreen — громкое предупреждение «окна не будет» (баг «логи идут, окна нет»)."""
    warning = invisible_platform_warning("offscreen")
    assert warning is not None
    assert "не появится" in warning
    assert "QT_QPA_PLATFORM" in warning


def test_invisible_platform_warning_visible_platforms() -> None:
    assert invisible_platform_warning("xcb") is None
    assert invisible_platform_warning("wayland") is None


def test_parse_args_flags() -> None:
    args = parse_args([])
    assert args.demo is False
    assert args.showcase is None  # без флага показ не включается
    assert args.demo_events is False
    args = parse_args(["--demo", "--demo-events"])
    assert args.demo is True
    assert args.demo_events is True


def test_parse_args_frame_stats() -> None:
    """--show-frame-stats: анализатор модели выключен по умолчанию."""
    assert parse_args([]).show_frame_stats is False
    assert parse_args(["--show-frame-stats"]).show_frame_stats is True


def test_states_with_clips_keeps_states_with_prefixes() -> None:
    available = states_with_clips(["Idle/Happy", "Walk/Normal", "Sleep/Calm"])
    assert available == {CharacterState.IDLE, CharacterState.WALK, CharacterState.SLEEP}


def test_states_with_clips_empty_input() -> None:
    # пусто — FSM добавит IDLE сам; поведение без клипов не включается (NF-P3.5)
    assert states_with_clips([]) == set()


def test_states_with_clips_none_logs_single_info(caplog: pytest.LogCaptureFixture) -> None:
    """Welcome-only: одна info-строка вместо предупреждения по состоянию (2026-10-10)."""
    with caplog.at_level(logging.INFO, logger="microchel.desktop.main"):
        assert states_with_clips(["Welcome/Normal"]) == set()
    records = [record for record in caplog.records if record.name == "microchel.desktop.main"]
    assert len(records) == 1
    assert records[0].levelname == "INFO"


def test_states_with_clips_partial_logs_single_warning(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Частично покрытые состояния — одна агрегированная строка warning."""
    with caplog.at_level(logging.INFO, logger="microchel.desktop.main"):
        available = states_with_clips(["Idle/Happy", "Walk/Normal"])
    assert available == {CharacterState.IDLE, CharacterState.WALK}
    records = [record for record in caplog.records if record.name == "microchel.desktop.main"]
    assert len(records) == 1
    assert records[0].levelname == "WARNING"
    assert "sleep" in records[0].getMessage()


def test_parse_args_showcase_flag() -> None:
    args = parse_args(["--showcase"])
    assert args.showcase is True
    assert args.demo is False


def test_parse_args_showcase_with_name() -> None:
    """ "--showcase dance" — только клипы по подстроке (case-insensitive)."""
    assert parse_args(["--showcase", "dance"]).showcase == "dance"
    assert parse_args(["--showcase", "--showcase-interval", "2"]).showcase is True


def test_parse_args_demo_and_showcase_mutually_exclusive() -> None:
    with pytest.raises(SystemExit):
        parse_args(["--demo", "--showcase"])


class FakeShowcaseWindow(QObject):
    """Фейк окна для showcase: сбор вызовов play_clip и move_by (PHASE 4)."""

    def __init__(
        self,
        names: list[str] | None = None,
        *,
        specs: dict[str, ClipSpec] | None = None,
        durations: tuple[int, ...] = (100, 100, 100, 100),
    ) -> None:
        super().__init__()
        self._names = names if names is not None else ["Walk/Normal", "Idle/Happy", "Blink/Happy"]
        self.clip_specs: dict[str, ClipSpec] = specs or {}
        self.durations = durations
        self.calls: list[dict[str, object]] = []
        self.moves: list[int] = []
        self.transition_calls: list[bool] = []
        self.idle_fallback_calls: list[bool] = []

    def available_clip_names(self) -> list[str]:
        return list(self._names)

    def clip_durations(self, name: str) -> tuple[int, ...] | None:
        if any(name.startswith(known) for known in self._names):
            return self.durations
        return None

    def play_clip(self, name: str, **kwargs: object) -> bool:
        self.calls.append({"name": name, **kwargs})
        return True

    def move_by(self, dx: int) -> bool:
        self.moves.append(dx)
        return True

    def set_transition_enabled(self, enabled: bool) -> None:
        self.transition_calls.append(bool(enabled))

    def set_idle_fallback_enabled(self, enabled: bool) -> None:
        self.idle_fallback_calls.append(bool(enabled))


def test_start_showcase_plays_all_clips_in_order(qtbot: QtBot) -> None:
    """Idle не показывается отдельным слотом; далее по алфавиту; restart по плану."""
    window = FakeShowcaseWindow()

    timer = start_showcase(window, pause_s=0.05)
    qtbot.waitUntil(lambda: len(window.calls) >= 3, timeout=3000)
    timer.stop()
    names = [call["name"] for call in window.calls]
    assert names == ["Blink/Happy", "Walk/Normal", "Blink/Happy"]
    first = window.calls[0]
    assert first["priority"] is Priority.EVENT
    assert first["restart"] is True
    # план без спеки: полный цикл одним проходом (loop=False — план конечен)
    assert first["loop"] is False
    assert first["frame_indices"] == (0, 1, 2, 3)


def test_start_showcase_idle_clips_skipped() -> None:
    """Idle-клипы исключены из показа (играют фоном, не слотом)."""
    window = FakeShowcaseWindow(["Idle/Happy", "Blink/Happy"])

    timer = start_showcase(window, pause_s=0.05)
    assert [call["name"] for call in window.calls] == ["Blink/Happy"]
    timer.stop()


def test_start_showcase_without_clips_timer_inactive() -> None:
    window = FakeShowcaseWindow([])
    timer = start_showcase(window)
    assert not timer.isActive()


def test_start_showcase_disables_transition() -> None:
    """Переход (MOVED CLIP) отключён: Move/Transition — обычный слот цикла."""
    window = FakeShowcaseWindow()

    timer = start_showcase(window, pause_s=0.05)
    assert window.transition_calls == [False]
    timer.stop()


def test_start_showcase_disables_idle_fallback() -> None:
    """Фоновая idle в паузах отключена: слот держится без фоновой анимации."""
    window = FakeShowcaseWindow()

    timer = start_showcase(window, pause_s=0.05)
    assert window.idle_fallback_calls == [False]
    timer.stop()


def test_start_showcase_only_filter_plays_matching_clips(qtbot: QtBot) -> None:
    """only="walk" — играют только клипы с подстрокой в имени (без учёта регистра)."""
    window = FakeShowcaseWindow(["Walk/Right", "Walk/Left", "Talk/Normal"])

    timer = start_showcase(window, pause_s=0.05, only="WALK")
    qtbot.waitUntil(lambda: len(window.calls) >= 2, timeout=3000)
    timer.stop()
    names = {call["name"] for call in window.calls}
    assert names == {"Walk/Right", "Walk/Left"}


def test_start_showcase_only_no_match_disables_showcase(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Нет клипов по маске — показ отключён с предупреждением, без запуска."""
    window = FakeShowcaseWindow(["Walk/Right"])
    with caplog.at_level(logging.WARNING, logger="microchel.desktop.main"):
        timer = start_showcase(window, only="dance")
    assert window.calls == []
    assert not timer.isActive()
    assert any("dance" in record.getMessage() for record in caplog.records)


def test_start_showcase_plays_full_clip_listing() -> None:
    """Полный лист кадров (фикс): план показа = все кадры клипа по порядку.

    loop-сегмент спеки не должен обрезать показ — иначе анимации «не
    проигрываются полностью» (например, 4 кадра из 10 при loop=[6, 9]).
    """
    spec = ClipSpec(name="Walk/Normal", frames=4, loop=(1, 2))
    window = FakeShowcaseWindow(["Walk/Normal"], specs={"Walk/Normal": spec})

    timer = start_showcase(window, pause_s=0.05)
    assert window.calls[0]["frame_indices"] == (0, 1, 2, 3)
    assert window.calls[0]["loop"] is False
    timer.stop()


def test_start_showcase_once_clip_plays_single_pass() -> None:
    """once=true — один проход всего клипа."""
    spec = ClipSpec(name="Blink/Happy", frames=4, once=True)
    window = FakeShowcaseWindow(["Blink/Happy"], specs={"Blink/Happy": spec})

    timer = start_showcase(window, pause_s=0.05)
    assert window.calls[0]["frame_indices"] == (0, 1, 2, 3)
    assert window.calls[0]["loop"] is False
    timer.stop()


def test_start_showcase_full_listing_ignores_repeat_fill() -> None:
    """repeat_fill_ms — рантайм-семантика FSM: в показе кадры не повторяются."""
    spec = ClipSpec(name="Angry/Normal", frames=4, loop=(0, 1), repeat_fill_ms=400)
    window = FakeShowcaseWindow(["Angry/Normal"], specs={"Angry/Normal": spec})

    timer = start_showcase(window, pause_s=0.05)
    assert window.calls[0]["frame_indices"] == (0, 1, 2, 3)
    timer.stop()


def test_start_showcase_slot_duration_uses_speed(qtbot: QtBot) -> None:
    """Слот = план / speed + пауза: следующая анимация через это время."""
    window = FakeShowcaseWindow(["Blink/Happy"])  # 4 кадра по 100 мс

    timer = start_showcase(window, pause_s=0.1, speed=2.0)
    # 400 мс / speed 2 + 100 мс паузы = 300 мс до следующей анимации
    assert timer.interval() == 300
    qtbot.waitUntil(lambda: len(window.calls) >= 2, timeout=3000)
    timer.stop()
    assert window.calls[1]["name"] == "Blink/Happy"  # цикл по одному клипу


def test_start_showcase_mirror_from_spec() -> None:
    """mirror="left" — план играется зеркально (правило спеки в рантайме)."""
    spec = ClipSpec(name="Walk/Direct", frames=4, loop=(1, 2), mirror="left")
    window = FakeShowcaseWindow(["Walk/Direct"], specs={"Walk/Direct": spec})

    timer = start_showcase(window, pause_s=0.05)
    assert window.calls[0]["mirror"] is True
    timer.stop()


def test_start_showcase_walk_motion_steps_window(qtbot: QtBot) -> None:
    """motion=walk: окно шагает во время клипа, направление влево для «left»."""
    spec = ClipSpec(name="Walk/Left", frames=4, loop=(0, 3), motion="walk")
    window = FakeShowcaseWindow(["Walk/Left"], specs={"Walk/Left": spec})

    timer = start_showcase(window, pause_s=1.0, walk_step_px=3, walk_interval_ms=5)
    qtbot.waitUntil(lambda: len(window.moves) > 0, timeout=3000)
    timer.stop()
    assert all(dx == -3 for dx in window.moves)


def test_start_showcase_no_motion_without_spec(qtbot: QtBot) -> None:
    """Без motion в спеке окно не двигается."""
    window = FakeShowcaseWindow(["Blink/Happy"])

    timer = start_showcase(window, pause_s=1.0, walk_interval_ms=5)
    qtbot.wait(200)
    timer.stop()
    assert window.moves == []


def test_parse_args_showcase_interval_default() -> None:
    args = parse_args(["--showcase"])
    assert args.showcase_interval == 0.0  # по умолчанию слоты подряд — стык плавный


def test_parse_args_showcase_interval_custom() -> None:
    args = parse_args(["--showcase", "--showcase-interval", "1.5"])
    assert args.showcase_interval == 1.5


def test_parse_args_showcase_interval_must_not_be_negative() -> None:
    assert parse_args(["--showcase-interval", "0"]).showcase_interval == 0.0
    with pytest.raises(SystemExit):
        parse_args(["--showcase-interval", "-1"])


def test_start_showcase_zero_pause_seam_is_playback_time() -> None:
    """Стык слотов без паузы: следующий слот стартует по времени проигрывания.

    Дополнительное мёртвое окно (пауза) между анимациями убирало плавность —
    старый кадр висел pause + длительность последнего кадра. Таймер слота —
    PreciseTimer: без досрочных выстрелов (CoarseTimer — до 5% раньше).
    """
    window = FakeShowcaseWindow(["Blink/Happy"])  # 4 кадра по 100 мс

    timer = start_showcase(window)  # pause_s по умолчанию 0
    assert timer.timerType() == Qt.TimerType.PreciseTimer
    assert timer.interval() == 400  # ровно проигрывание плана, без паузы
    timer.stop()


def test_parse_args_speed_and_scale_defaults() -> None:
    args = parse_args([])
    assert args.speed == 1.0
    assert args.pet_scale == pytest.approx(0.65)


def test_parse_args_speed_and_scale_custom() -> None:
    args = parse_args(["--speed", "0.5", "--pet-scale", "0.5"])
    assert args.speed == 0.5
    assert args.pet_scale == 0.5


def test_parse_args_speed_must_be_positive() -> None:
    with pytest.raises(SystemExit):
        parse_args(["--speed", "0"])


def test_parse_args_pet_scale_must_be_positive() -> None:
    with pytest.raises(SystemExit):
        parse_args(["--pet-scale", "-1"])
