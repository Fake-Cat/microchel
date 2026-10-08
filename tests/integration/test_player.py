"""Интеграционные тесты плеера анимаций (pytest-qt, PHASE 2)."""

from __future__ import annotations

from pathlib import Path

import pytest
from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap
from pytestqt.qtbot import QtBot

from microchel.animation.frames import AnimationClip, load_clip
from microchel.animation.player import AnimationPlayer
from microchel.animation.queue import Priority

FRAME_MS = 40  # короткие кадры, чтобы тесты были быстрыми


def _write_frame(path: Path, color: Qt.GlobalColor) -> None:
    pixmap = QPixmap(24, 24)
    pixmap.fill(color)
    assert pixmap.save(str(path), "PNG")


def _make_clip(root: Path, name: str, count: int, duration_ms: int = FRAME_MS) -> AnimationClip:
    """Создать реальный клип в tmp: root/<name>/State/1/_NNN_DDD.png."""
    line_dir = root / name / "State" / "1"
    line_dir.mkdir(parents=True)
    for index in range(count):
        _write_frame(line_dir / f"_{index:03d}_{duration_ms}.png", Qt.GlobalColor.red)
    return load_clip(line_dir)


@pytest.fixture
def clips(tmp_path: Path) -> dict[str, AnimationClip]:
    return {
        "idle": _make_clip(tmp_path, "Idle", count=4),
        "blink": _make_clip(tmp_path, "Blink", count=3),
        "walk": _make_clip(tmp_path, "Walk", count=3),
    }


@pytest.fixture
def player(qtbot: QtBot) -> AnimationPlayer:
    del qtbot  # приложение уже создано qtbot-ом; parent у плеера не нужен
    return AnimationPlayer()


class TestPlayback:
    def test_first_frame_shown_immediately(
        self, player: AnimationPlayer, clips: dict[str, AnimationClip]
    ) -> None:
        received: list[object] = []
        player.frame_changed.connect(received.append)
        player.play(clips["idle"])
        assert len(received) == 1
        assert player.frame_pixmap is not None
        assert player.frame_index == 0
        assert player.is_playing
        assert player.current_clip is not None

    def test_advances_through_frames(
        self, qtbot: QtBot, player: AnimationPlayer, clips: dict[str, AnimationClip]
    ) -> None:
        player.play(clips["idle"])
        with qtbot.waitSignal(player.frame_changed, timeout=1000):
            pass  # таймер сам сдвинет кадр
        assert player.frame_index >= 1

    def test_frame_timings_from_filename(
        self, qtbot: QtBot, player: AnimationPlayer, tmp_path: Path
    ) -> None:
        """Длительность кадра — из имени файла (ADR-005): 3 кадра по 300 мс."""
        clip = _make_clip(tmp_path, "Slow", count=3, duration_ms=300)
        player.play(clip)
        # через 150 мс кадр ещё не сменился (300 > 150)
        qtbot.wait(150)
        assert player.frame_index == 0
        # а к 650 мс — уже сменился минимум один раз
        qtbot.wait(500)
        assert player.frame_index >= 1

    def test_finish_emits_and_returns_to_idle(
        self, qtbot: QtBot, player: AnimationPlayer, clips: dict[str, AnimationClip]
    ) -> None:
        player.set_idle(clips["idle"])
        player.play(clips["idle"])  # idle уже играет
        with qtbot.waitSignal(player.animation_finished, timeout=2000):
            player.play(clips["blink"], priority=Priority.EVENT, loop=False)
        qtbot.wait(50)  # дать плееру перейти к idle после finished
        assert player.current_clip is not None
        assert player.current_clip.name == "Idle/State"

    def test_loop_count_two_completes(
        self, qtbot: QtBot, player: AnimationPlayer, clips: dict[str, AnimationClip]
    ) -> None:
        with qtbot.waitSignal(player.animation_finished, timeout=2000):
            player.play(clips["walk"], loop=2)
        assert player.current_clip is None or player.current_clip.name != "Walk/State"

    def test_infinite_loop_never_finishes(
        self, qtbot: QtBot, player: AnimationPlayer, clips: dict[str, AnimationClip]
    ) -> None:
        finished: list[str] = []
        player.animation_finished.connect(finished.append)
        player.play(clips["idle"], loop=True)
        qtbot.wait(FRAME_MS * 10)
        assert finished == []


class TestTransitions:
    def test_same_clip_not_restarted(
        self, qtbot: QtBot, player: AnimationPlayer, clips: dict[str, AnimationClip]
    ) -> None:
        """Повторный play той же анимации без restart не сбрасывает кадр (FR-P2.4)."""
        player.play(clips["idle"], priority=Priority.IDLE)
        qtbot.wait(FRAME_MS + 30)  # хотя бы один кадр пройден
        assert player.frame_index >= 1
        position_before = player.frame_index
        player.play(clips["idle"], priority=Priority.IDLE)  # без restart
        assert player.frame_index == position_before  # кадр не сброшен
        assert player.pending is None

    def test_higher_priority_interrupts_on_frame_boundary(
        self, qtbot: QtBot, player: AnimationPlayer, clips: dict[str, AnimationClip]
    ) -> None:
        player.play(clips["idle"], priority=Priority.IDLE)
        player.play(clips["blink"], priority=Priority.EVENT, loop=False)
        # до границы кадра blink ещё не начался — ждём pending
        assert player.pending is not None or (
            player.current_clip is not None and player.current_clip.name == "Blink/State"
        )
        qtbot.waitUntil(
            lambda: player.current_clip is not None
            and player.current_clip.name == "Blink/State",
            timeout=2000,
        )

    def test_equal_priority_goes_to_queue(
        self, qtbot: QtBot, player: AnimationPlayer, clips: dict[str, AnimationClip]
    ) -> None:
        # ничего не играет → первый play стартует сразу
        player.play(clips["idle"], priority=Priority.BEHAVIOR)
        player.play(clips["walk"], priority=Priority.BEHAVIOR)
        # walk в очереди: текущая анимация всё ещё idle
        assert player.current_clip is not None
        assert player.current_clip.name == "Idle/State"
