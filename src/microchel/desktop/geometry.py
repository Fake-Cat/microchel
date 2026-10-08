"""Геометрия окна персонажа: зажим координат в пределах экрана.

Чистые функции без Qt-событий — тестируются юнит-тестами.
"""

from __future__ import annotations

from collections.abc import Iterable

from PySide6.QtCore import QPoint, QRect, QSize


def clamp_axis(value: int, low: int, extent: int, size: int) -> int:
    """Зажать координату так, чтобы отрезок [value, value+size] лежал в [low, low+extent].

    Если size >= extent, прижимаем к началу области.
    """
    if size >= extent:
        return low
    max_value = low + extent - size
    return min(max(value, low), max_value)


def clamp_to_screen(pos: QPoint, size: QSize, screen: QRect) -> QPoint:
    """Зажать позицию окна размера size так, чтобы оно целиком было в screen."""
    x = clamp_axis(pos.x(), screen.x(), screen.width(), size.width())
    y = clamp_axis(pos.y(), screen.y(), screen.height(), size.height())
    return QPoint(x, y)


def desktop_area(rects: Iterable[QRect]) -> QRect:
    """Объединённая рабочая область всех экранов (мультимониторный bbox).

    Нужна, чтобы пит мог перетаскиваться между мониторами: зажим не в
    геометрию одного экрана, а в общий предел всех. Пустой вход — пустой QRect.
    """
    area = QRect()
    for rect in rects:
        area = area.united(rect)
    return area
