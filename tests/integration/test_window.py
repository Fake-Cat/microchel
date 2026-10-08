"""Тесты окна персонажа (pytest-qt, offscreen-платформа)."""

from __future__ import annotations

from pathlib import Path

import pytest
from PySide6.QtCore import QEvent, QPoint, QPointF, Qt
from PySide6.QtGui import QMouseEvent
from PySide6.QtWidgets import QApplication
from pytestqt.qtbot import QtBot

from microchel.animation.queue import Priority
from microchel.common.event_bus import EventBus
from microchel.common.events import UserEvent, UserEventKind
from microchel.desktop.geometry import desktop_area
from microchel.desktop.window import PetWindow

SPRITE = Path(__file__).resolve().parents[2] / "assets" / "characters" / "test" / "test_idle.png"


@pytest.fixture
def pet_window(qtbot: QtBot) -> PetWindow:
    window = PetWindow(sprite_path=SPRITE)
    qtbot.addWidget(window)
    window.show()
    return window


@pytest.fixture
def bus() -> EventBus:
    return EventBus()


@pytest.fixture
def bus_window(qtbot: QtBot, bus: EventBus) -> PetWindow:
    """Окно, подключённое к шине (PHASE 3: клик/драг → UserEvent)."""
    window = PetWindow(sprite_path=SPRITE, bus=bus)
    qtbot.addWidget(window)
    window.show()
    return window


def _send_mouse(
    window: PetWindow,
    event_type: QEvent.Type,
    pos: QPoint,
    *,
    button: Qt.MouseButton,
    buttons: Qt.MouseButton,
) -> None:
    """Отправить мышиное событие окну с корректными глобальными координатами (FR-P3.5)."""
    event = QMouseEvent(
        event_type,
        QPointF(pos),
        QPointF(window.mapToGlobal(pos)),
        button,
        buttons,
        Qt.KeyboardModifier.NoModifier,
    )
    QApplication.sendEvent(window, event)


class TestWindowFlags:
    def test_frameless(self, pet_window: PetWindow) -> None:
        assert pet_window.windowFlags() & Qt.WindowType.FramelessWindowHint

    def test_always_on_top(self, pet_window: PetWindow) -> None:
        assert pet_window.windowFlags() & Qt.WindowType.WindowStaysOnTopHint

    def test_translucent_background(self, pet_window: PetWindow) -> None:
        assert pet_window.testAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)

    def test_sprite_loaded(self, pet_window: PetWindow) -> None:
        assert not pet_window._sprite.isNull()


class TestMoveClamped:
    def test_inside_keeps_position(self, pet_window: PetWindow) -> None:
        pet_window.move_clamped(QPoint(10, 10))
        assert pet_window.pos() == QPoint(10, 10)

    def test_negative_clamped(self, pet_window: PetWindow) -> None:
        pet_window.move_clamped(QPoint(-100, -100))
        assert pet_window.pos().x() >= 0
        assert pet_window.pos().y() >= 0

    def test_far_position_clamped_to_all_screens(self, pet_window: PetWindow) -> None:
        # зажим в объединение всех экранов (мультимониторный предел)
        pet_window.move_clamped(QPoint(100_000, 100_000))
        area = desktop_area(s.availableGeometry() for s in QApplication.screens())
        assert pet_window.pos().x() <= area.x() + area.width() - pet_window.width()
        assert pet_window.pos().y() <= area.y() + area.height() - pet_window.height()


class TestContextMenu:
    def test_menu_contains_quit(self, pet_window: PetWindow) -> None:
        menu = pet_window.build_menu()
        assert [action.text() for action in menu.actions()] == ["Выход"]

    def test_window_visible_after_show(self, pet_window: PetWindow) -> None:
        assert pet_window.isVisible()


class TestAnimationIntegration:
    def test_setup_animation_connects_player(self, pet_window: PetWindow) -> None:
        # ассеты проекта: assets/characters/test/{Idle,Blink,Walk}/...
        assert pet_window.setup_animation() is True
        assert pet_window.player is not None
        names = pet_window.available_clip_names()
        assert any(name.startswith("Idle/") for name in names)
        # первый кадр показан сразу
        assert pet_window.player.frame_pixmap is not None
        assert pet_window.player.current_clip is not None
        assert pet_window.player.current_clip.name.startswith("Idle/")

    def test_empty_root_falls_back_to_static_sprite(self, pet_window: PetWindow) -> None:
        assert pet_window.setup_animation(Path("/nonexistent-root")) is False
        assert pet_window.player is None

    def test_play_clip_by_prefix(self, pet_window: PetWindow) -> None:
        assert pet_window.setup_animation() is True
        # Blink — приоритетнее idle, прерывает на границе кадра
        assert pet_window.play_clip("Blink/", priority=Priority.EVENT, loop=False) is True
        assert pet_window.player is not None
        assert (
            pet_window.player.pending is not None
            or (
                pet_window.player.current_clip is not None
                and pet_window.player.current_clip.name.startswith("Blink/")
            )
        )

    def test_play_clip_unknown_prefix_returns_false(self, pet_window: PetWindow) -> None:
        assert pet_window.setup_animation() is True
        assert pet_window.play_clip("DoesNotExist/") is False


class TestMoveBy:
    def test_move_by_shifts_position(self, pet_window: PetWindow) -> None:
        pet_window.move_clamped(QPoint(10, 10))
        assert pet_window.move_by(5) is True
        assert pet_window.pos().x() == 15

    def test_move_by_blocked_at_edge_returns_false(self, pet_window: PetWindow) -> None:
        pet_window.move_clamped(QPoint(0, 10))
        assert pet_window.move_by(-50) is False  # позиция не изменилась → разворот (FR-P3.4)


class TestUserEventsToBus:
    """Клик/драг → события в шину (FR-P3.5)."""

    @staticmethod
    def _press(window: PetWindow, pos: QPoint) -> None:
        _send_mouse(
            window,
            QEvent.Type.MouseButtonPress,
            pos,
            button=Qt.MouseButton.LeftButton,
            buttons=Qt.MouseButton.LeftButton,
        )

    @staticmethod
    def _move(window: PetWindow, pos: QPoint) -> None:
        _send_mouse(
            window,
            QEvent.Type.MouseMove,
            pos,
            button=Qt.MouseButton.NoButton,
            buttons=Qt.MouseButton.LeftButton,
        )

    @staticmethod
    def _release(window: PetWindow, pos: QPoint) -> None:
        _send_mouse(
            window,
            QEvent.Type.MouseButtonRelease,
            pos,
            button=Qt.MouseButton.LeftButton,
            buttons=Qt.MouseButton.NoButton,
        )

    @staticmethod
    def _kinds(bus: EventBus) -> list[UserEventKind]:
        received: list[UserEventKind] = []
        bus.subscribe(UserEvent, lambda e: received.append(e.kind))
        return received

    def test_click_without_move(self, bus_window: PetWindow, bus: EventBus) -> None:
        kinds = self._kinds(bus)
        pos = QPoint(30, 30)
        self._press(bus_window, pos)
        self._release(bus_window, pos)
        assert kinds == [UserEventKind.CLICK]

    def test_drag_emits_start_then_end(self, bus_window: PetWindow, bus: EventBus) -> None:
        kinds = self._kinds(bus)
        self._press(bus_window, QPoint(30, 30))
        self._move(bus_window, QPoint(50, 50))  # смещение ≥ порога
        self._release(bus_window, QPoint(50, 50))
        assert kinds == [UserEventKind.DRAG_START, UserEventKind.DRAG_END]

    def test_jitter_below_threshold_is_click(self, bus_window: PetWindow, bus: EventBus) -> None:
        kinds = self._kinds(bus)
        self._press(bus_window, QPoint(30, 30))
        self._move(bus_window, QPoint(31, 31))  # дрожание 2 px < порога 5
        self._release(bus_window, QPoint(31, 31))
        assert kinds == [UserEventKind.CLICK]

    def test_without_bus_no_error(self, pet_window: PetWindow) -> None:
        pos = QPoint(30, 30)
        self._press(pet_window, pos)
        self._release(pet_window, pos)  # шины нет — событие просто не отправляется
