"""Тесты логики точки входа (без создания QApplication)."""

from __future__ import annotations

from microchel.desktop.main import select_qt_platform

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
