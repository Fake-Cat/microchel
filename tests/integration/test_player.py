"""Интеграционные тесты плеера анимаций (pytest-qt, PHASE 2)."""

from __future__ import annotations

from pathlib import Path

import pytest
from PySide6.QtCore import Qt
from PySide6.QtGui import QPainter, QPixmap
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


class TestMirror:
    """Зеркальный показ кадров (спека mirror="left", PHASE 4)."""

    @staticmethod
    def _make_asymmetric_clip(root: Path) -> AnimationClip:
        """Кадр с красной полосой у ЛЕВОГО края — видно направление флипа."""
        line_dir = root / "Side" / "State" / "1"
        line_dir.mkdir(parents=True)
        pixmap = QPixmap(24, 24)
        pixmap.fill(Qt.GlobalColor.transparent)
        painter = QPainter(pixmap)
        painter.fillRect(0, 0, 6, 24, Qt.GlobalColor.red)
        painter.end()
        assert pixmap.save(str(line_dir / "_000_500.png"), "PNG")
        return load_clip(line_dir)

    def test_mirror_flips_frame_horizontally(self, player: AnimationPlayer, tmp_path: Path) -> None:
        clip = self._make_asymmetric_clip(tmp_path)
        received: list[QPixmap] = []
        player.frame_changed.connect(received.append)

        player.play(clip, mirror=True)

        assert player.is_mirrored is True
        assert len(received) == 1
        image = received[0].toImage()
        # полоса была слева → после флипа справа
        assert image.pixelColor(20, 12) == Qt.GlobalColor.red
        assert image.pixelColor(2, 12).alpha() == 0

    def test_without_mirror_frame_unchanged(self, player: AnimationPlayer, tmp_path: Path) -> None:
        clip = self._make_asymmetric_clip(tmp_path)
        received: list[QPixmap] = []
        player.frame_changed.connect(received.append)

        player.play(clip)

        assert player.is_mirrored is False
        image = received[0].toImage()
        assert image.pixelColor(2, 12) == Qt.GlobalColor.red
        assert image.pixelColor(20, 12).alpha() == 0


class TestTransition:
    """Переходный клип (MOVED CLIP): каждая смена анимации начинается с него."""

    def test_change_starts_with_transition(
        self, qtbot: QtBot, player: AnimationPlayer, clips: dict[str, AnimationClip], tmp_path: Path
    ) -> None:
        transition = _make_clip(tmp_path, "Move", count=3)
        player.set_transition(transition)
        player.set_idle(clips["idle"])
        player.play(clips["idle"])  # первый старт — без перехода
        assert player.current_clip is not None
        assert player.current_clip.name == "Idle/State"
        player.play(clips["blink"], restart=True, loop=False)
        # смена анимации: сразу играется переход, цель — после него
        assert player.current_clip is not None
        assert player.current_clip.name == "Move/State"
        qtbot.waitUntil(
            lambda: player.current_clip is not None and player.current_clip.name == "Blink/State",
            timeout=2000,
        )

    def test_transition_never_emits_finished(
        self, qtbot: QtBot, player: AnimationPlayer, clips: dict[str, AnimationClip], tmp_path: Path
    ) -> None:
        """Конец перехода — не конец анимации: иначе controller перезапустит состояние."""
        transition = _make_clip(tmp_path, "Move", count=3)
        player.set_transition(transition)
        player.set_idle(clips["idle"])
        finished: list[str] = []
        player.animation_finished.connect(finished.append)
        player.play(clips["idle"])
        player.play(clips["blink"], restart=True, loop=False)
        # blink отыграет → возврат к idle (тоже через переход)
        qtbot.waitUntil(
            lambda: player.current_clip is not None and player.current_clip.name == "Idle/State",
            timeout=3000,
        )
        qtbot.wait(100)  # дать перепроверить, что хвосты отработали
        assert "Move/State" not in finished
        assert "Blink/State" in finished

    def test_same_clip_restart_without_transition(
        self, player: AnimationPlayer, clips: dict[str, AnimationClip], tmp_path: Path
    ) -> None:
        """Перезапуск того же клипа — не смена, переход не вставляется."""
        transition = _make_clip(tmp_path, "Move", count=3)
        player.set_transition(transition)
        player.play(clips["idle"])
        player.play(clips["idle"], restart=True)
        assert player.current_clip is not None
        assert player.current_clip.name == "Idle/State"


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
            lambda: player.current_clip is not None and player.current_clip.name == "Blink/State",
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

    def test_restart_replaces_other_clip_immediately(
        self, player: AnimationPlayer, clips: dict[str, AnimationClip]
    ) -> None:
        """restart=True — немедленная замена даже другого клипа (PHASE 3: смена состояний)."""
        player.play(clips["idle"], priority=Priority.IDLE)
        player.play(clips["walk"], priority=Priority.IDLE, restart=True)
        assert player.current_clip is not None
        assert player.current_clip.name == "Walk/State"
        assert player.pending is None

    def test_finished_listener_clip_not_replaced_by_idle(
        self, qtbot: QtBot, player: AnimationPlayer, clips: dict[str, AnimationClip]
    ) -> None:
        """Клип, запущенный слушателем animation_finished, не перетирается idle-фоллбэком."""
        player.set_idle(clips["idle"])
        player.play(clips["blink"], priority=Priority.EVENT, loop=False)

        def resume(_name: str) -> None:
            player.play(clips["walk"], priority=Priority.BEHAVIOR, loop=True, restart=True)

        player.animation_finished.connect(resume)
        qtbot.waitUntil(
            lambda: player.current_clip is not None and player.current_clip.name == "Walk/State",
            timeout=2000,
        )
        qtbot.wait(FRAME_MS * 3)  # idle-фоллбэк успел бы перетёреть, если бы мог
        assert player.current_clip is not None
        assert player.current_clip.name == "Walk/State"


class TestSpeed:
    """Множитель скорости кадров (PHASE 4, --speed): duration / speed."""

    def test_default_speed_is_one(
        self, player: AnimationPlayer, clips: dict[str, AnimationClip]
    ) -> None:
        player.play(clips["idle"])
        assert player.speed == 1.0
        assert player._timer.interval() == FRAME_MS  # без деления

    def test_speed_two_halves_frame_duration(self, player: AnimationPlayer, tmp_path: Path) -> None:
        clip = _make_clip(tmp_path, "Quick", count=2, duration_ms=300)
        player.play(clip, speed=2.0)
        assert player.speed == 2.0
        assert player._timer.interval() == 150  # 300 мс / 2

    def test_slow_speed_doubles_frame_duration(
        self, player: AnimationPlayer, tmp_path: Path
    ) -> None:
        clip = _make_clip(tmp_path, "Slow", count=2, duration_ms=300)
        player.play(clip, speed=0.5)
        assert player.speed == 0.5
        assert player._timer.interval() == 600  # 300 мс / 0.5

    def test_speed_advances_frames_faster(
        self, qtbot: QtBot, player: AnimationPlayer, tmp_path: Path
    ) -> None:
        """При speed=2 кадр 300 мс сменяется раньше, чем за 200 мс."""
        clip = _make_clip(tmp_path, "Quick2", count=3, duration_ms=300)
        player.play(clip, speed=2.0)
        qtbot.wait(200)
        assert player.frame_index >= 1


class TestTiming:
    """Точность темпа кадров (фикс стыков анимаций, 2026-10-11)."""

    def test_frame_timer_is_precise(self, player: AnimationPlayer) -> None:
        """Таймер кадров — PreciseTimer.

        Qt CoarseTimer стреляет до 5% раньше срока — кадры и стыки слотов
        «съедались», анимации выглядели обрезанными.
        """
        assert player._timer.timerType() == Qt.TimerType.PreciseTimer
