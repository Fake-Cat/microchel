"""Юнит-тесты зажима координат окна."""

from __future__ import annotations

from PySide6.QtCore import QPoint, QRect, QSize

from microchel.desktop.geometry import clamp_axis, clamp_to_screen, desktop_area


class TestClampAxis:
    def test_inside_area_unchanged(self) -> None:
        assert clamp_axis(50, low=0, extent=1000, size=100) == 50

    def test_clamped_to_low(self) -> None:
        assert clamp_axis(-20, low=0, extent=1000, size=100) == 0

    def test_clamped_to_max(self) -> None:
        assert clamp_axis(999, low=0, extent=1000, size=100) == 900

    def test_exact_edge(self) -> None:
        assert clamp_axis(900, low=0, extent=1000, size=100) == 900

    def test_screen_offset_respected(self) -> None:
        assert clamp_axis(-5, low=100, extent=500, size=50) == 100

    def test_size_bigger_than_area_pins_to_low(self) -> None:
        assert clamp_axis(200, low=0, extent=100, size=200) == 0


class TestClampToScreen:
    def test_inside_unchanged(self) -> None:
        pos = QPoint(300, 200)
        result = clamp_to_screen(pos, QSize(100, 100), QRect(0, 0, 1920, 1080))
        assert result == QPoint(300, 200)

    def test_negative_clamped(self) -> None:
        result = clamp_to_screen(QPoint(-50, -50), QSize(100, 100), QRect(0, 0, 1920, 1080))
        assert result == QPoint(0, 0)

    def test_bottom_right_clamped(self) -> None:
        result = clamp_to_screen(QPoint(5000, 5000), QSize(100, 100), QRect(0, 0, 1920, 1080))
        assert result == QPoint(1820, 980)

    def test_multi_monitor_offset(self) -> None:
        # экран начинается с (2000, 0) — второй монитор
        result = clamp_to_screen(QPoint(1900, 10), QSize(100, 100), QRect(2000, 0, 1920, 1080))
        assert result == QPoint(2000, 10)


class TestDesktopArea:
    def test_two_monitors_united(self) -> None:
        left = QRect(0, 0, 1920, 1080)
        right = QRect(1920, 0, 2560, 1440)
        area = desktop_area([left, right])
        assert area == QRect(0, 0, 4480, 1440)

    def test_single_monitor(self) -> None:
        rect = QRect(100, 50, 1920, 1080)
        assert desktop_area([rect]) == rect

    def test_empty_input_gives_empty_rect(self) -> None:
        assert desktop_area([]).isEmpty()

    def test_monitor_above_left_of_origin(self) -> None:
        # монитор слева/сверху — отрицательные координаты, правая/нижняя границы
        # считаются по всем прямоугольникам (тут левый ниже опускается до 1224)
        main = QRect(0, 0, 1920, 1080)
        left = QRect(-1280, 200, 1280, 1024)
        area = desktop_area([main, left])
        assert area == QRect(-1280, 0, 3200, 1224)

    def test_clamp_into_united_area_allows_crossing_boundary(self) -> None:
        # пит на границе мониторов: в объединённой области переход разрешён
        area = desktop_area([QRect(0, 0, 1920, 1080), QRect(1920, 0, 1920, 1080)])
        result = clamp_to_screen(QPoint(1900, 100), QSize(160, 160), area)
        assert result == QPoint(1900, 100)  # в одиночном экране пришлось бы 1760
