"""Сгенерировать тестовый набор анимаций (PHASE 2) в формате _NNN_DDD.png (ADR-005).

Материал собственный, временный — права не вопрос.
Структура: assets/characters/test/<Анимация>/<Состояние>/<Линия>/_NNN_DDD.png
Запуск: .venv/bin/python scripts/make_test_animations.py
"""

from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QGuiApplication, QPainter, QPen, QPixmap

SIZE = 160
ROOT = Path(__file__).resolve().parents[1] / "assets" / "characters" / "test"

BODY = QColor("#7ec8e3")
OUTLINE = QColor("#2b2b2b")
SKIN = QColor("#ffe3c7")
HAIR = QColor("#5a3e2b")

# (каталог клипа относительно ROOT, кадры: (длительность_мс, параметры))
CLIPS: dict[str, list[tuple[int, dict[str, float | bool]]]] = {
    "Idle/Happy/1": [
        (250, {"breath": 0}),
        (250, {"breath": 2}),
        (250, {"breath": 4}),
        (250, {"breath": 4}),
        (250, {"breath": 2}),
        (375, {"breath": 0}),
    ],
    "Blink/Happy/1": [
        (125, {"eyes": "open"}),
        (60, {"eyes": "half"}),
        (75, {"eyes": "closed"}),
        (60, {"eyes": "half"}),
        (250, {"eyes": "open"}),
    ],
    "Walk/Normal/1": [
        (125, {"step": 0, "lean": 0}),
        (125, {"step": 3, "lean": 1}),
        (125, {"step": 6, "lean": 0}),
        (125, {"step": 3, "lean": -1}),
        (125, {"step": 0, "lean": 0}),
        (125, {"step": -3, "lean": 1}),
    ],
}


def render_frame(size: int, *, breath: float = 0, eyes: str = "open", step: float = 0,
                 lean: float = 0) -> QPixmap:
    """Нарисовать кадр фигурки-заглушки с прозрачным фоном."""
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.GlobalColor.transparent)

    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    try:
        painter.translate(lean, -breath)
        painter.setPen(QPen(QColor(OUTLINE), 3))

        painter.setBrush(BODY)
        painter.drawRoundedRect(QRectF(size * 0.28, size * 0.45, size * 0.44, size * 0.45), 24, 24)

        painter.setBrush(SKIN)
        painter.drawEllipse(QRectF(size * 0.2, size * 0.1, size * 0.6, size * 0.5))

        painter.setBrush(HAIR)
        painter.drawArc(QRectF(size * 0.19, size * 0.07, size * 0.62, size * 0.3), 0, 180 * 16)

        # глаза (мигание)
        painter.setBrush(QColor(OUTLINE))
        painter.setPen(Qt.PenStyle.NoPen)
        eye_y = size * 0.33
        if eyes == "closed":
            painter.setPen(QPen(QColor(OUTLINE), 2))
            painter.drawLine(QPointF(size * 0.33, eye_y), QPointF(size * 0.43, eye_y))
            painter.drawLine(QPointF(size * 0.57, eye_y), QPointF(size * 0.67, eye_y))
        elif eyes == "half":
            painter.drawEllipse(QPointF(size * 0.38, eye_y), 5, 4)
            painter.drawEllipse(QPointF(size * 0.62, eye_y), 5, 4)
        else:
            painter.drawEllipse(QPointF(size * 0.38, eye_y), 5, 7)
            painter.drawEllipse(QPointF(size * 0.62, eye_y), 5, 7)

        painter.setPen(QPen(QColor(OUTLINE), 2))
        smile = QRectF(size * 0.42, size * 0.35, size * 0.16, size * 0.12)
        painter.drawArc(smile, 180 * 16, 180 * 16)

        # «ноги» (шаг)
        foot_y = size * 0.9
        left_x = size * 0.4 - step
        right_x = size * 0.6 + step
        painter.drawLine(QPointF(left_x, foot_y), QPointF(left_x, size * 0.98))
        painter.drawLine(QPointF(right_x, foot_y), QPointF(right_x, size * 0.98))
    finally:
        painter.end()
    return pixmap


def main() -> int:
    QGuiApplication(sys.argv)  # нужен для QPixmap
    written = 0
    for rel_dir, frames in CLIPS.items():
        out_dir = ROOT / rel_dir
        out_dir.mkdir(parents=True, exist_ok=True)
        for index, (duration_ms, params) in enumerate(frames):
            out_path = out_dir / f"_{index:03d}_{duration_ms}.png"
            pixmap = render_frame(SIZE, **params)
            if not pixmap.save(str(out_path), "PNG"):
                print(f"Не удалось сохранить: {out_path}", file=sys.stderr)
                return 1
            written += 1
        print(f"Клип сохранён: {out_dir} ({len(frames)} кадров)")
    print(f"Всего кадров: {written}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
