"""Тесты окна персонажа (pytest-qt, offscreen-платформа)."""

from __future__ import annotations

from pathlib import Path

import pytest
from PySide6.QtCore import QPoint, Qt
from PySide6.QtWidgets import QApplication
from pytestqt.qtbot import QtBot

from microchel.animation.queue import Priority
from microchel.desktop.geometry import desktop_area
from microchel.desktop.window import PetWindow

SPRITE = Path(__file__).resolve().parents[2] / "assets" / "characters" / "test" / "test_idle.png"


@pytest.fixture
def pet_window(qtbot: QtBot) -> PetWindow:
    window = PetWindow(sprite_path=SPRITE)
    qtbot.addWidget(window)
    window.show()
    return window


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
