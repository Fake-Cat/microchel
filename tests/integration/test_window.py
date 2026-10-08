"""Тесты окна персонажа (pytest-qt, offscreen-платформа)."""

from __future__ import annotations

from pathlib import Path

import pytest
from PySide6.QtCore import QPoint, Qt
from PySide6.QtWidgets import QApplication
from pytestqt.qtbot import QtBot

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
