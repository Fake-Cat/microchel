"""Сгенерировать тестовый спрайт персонажа (PHASE 1).

Материал собственный, временный — права не вопрос.
Запуск: .venv/bin/python scripts/make_test_sprite.py
"""

from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QGuiApplication, QPainter, QPen, QPixmap

SIZE = 160
OUT_PATH = Path(__file__).resolve().parents[1] / "assets" / "characters" / "test" / "test_idle.png"


def render_sprite(size: int = SIZE) -> QPixmap:
    """Нарисовать простую фигурку-заглушку (chibi) с прозрачным фоном."""
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.GlobalColor.transparent)

    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    try:
        body_color = QColor("#7ec8e3")
        outline = QPen(QColor("#2b2b2b"), 3)
        painter.setPen(outline)

        # тело (туловище-капля)
        painter.setBrush(body_color)
        body = QRectF(size * 0.28, size * 0.45, size * 0.44, size * 0.45)
        painter.drawRoundedRect(body, 24, 24)

        # голова
        painter.setBrush(QColor("#ffe3c7"))
        head = QRectF(size * 0.2, size * 0.1, size * 0.6, size * 0.5)
        painter.drawEllipse(head)

        # «волосы»
        painter.setBrush(QColor("#5a3e2b"))
        hair = QRectF(size * 0.19, size * 0.07, size * 0.62, size * 0.3)
        painter.drawArc(hair, 0, 180 * 16)

        # глаза
        painter.setBrush(QColor("#2b2b2b"))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawEllipse(QPointF(size * 0.38, size * 0.33), 5, 7)
        painter.drawEllipse(QPointF(size * 0.62, size * 0.33), 5, 7)

        # улыбка
        painter.setPen(QPen(QColor("#2b2b2b"), 2))
        smile = QRectF(size * 0.42, size * 0.35, size * 0.16, size * 0.12)
        painter.drawArc(smile, 180 * 16, 180 * 16)

        # антенна
        painter.setPen(QPen(QColor("#2b2b2b"), 2))
        painter.drawLine(QPointF(size * 0.5, size * 0.1), QPointF(size * 0.5, size * 0.02))
        painter.setBrush(QColor("#e36e6e"))
        painter.drawEllipse(QPointF(size * 0.5, size * 0.02), 4, 4)
    finally:
        painter.end()
    return pixmap


def main() -> int:
    QGuiApplication(sys.argv)  # нужен для QPixmap
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    pixmap = render_sprite()
    if not pixmap.save(str(OUT_PATH), "PNG"):
        print(f"Не удалось сохранить: {OUT_PATH}", file=sys.stderr)
        return 1
    print(f"Спрайт сохранён: {OUT_PATH} ({pixmap.width()}x{pixmap.height()})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

