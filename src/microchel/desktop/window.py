"""Окно персонажа (PHASE 1): frameless, прозрачное, перетаскиваемое."""

from __future__ import annotations

import logging
from pathlib import Path

from PySide6.QtCore import QPoint, Qt
from PySide6.QtGui import QContextMenuEvent, QMouseEvent, QPainter, QPaintEvent, QPixmap
from PySide6.QtWidgets import QApplication, QMenu, QWidget

from microchel.desktop.geometry import clamp_to_screen, desktop_area

logger = logging.getLogger(__name__)

DEFAULT_SPRITE = (
    Path(__file__).resolve().parents[3] / "assets" / "characters" / "test" / "test_idle.png"
)
DEFAULT_SIZE = 160


class PetWindow(QWidget):
    """Прозрачное окно с тестовым спрайтом и перетаскиванием."""

    def __init__(self, sprite_path: Path | None = None, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._drag_offset: QPoint | None = None
        self._sprite_path = sprite_path or DEFAULT_SPRITE
        self._sprite = QPixmap(str(self._sprite_path))
        if self._sprite.isNull():
            logger.warning("Спрайт не загружен: %s (временная заглушка)", self._sprite_path)

        self.setWindowTitle("Microchel")
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setMinimumSize(64, 64)
        self.resize(DEFAULT_SIZE, DEFAULT_SIZE)

    # --- отрисовка -----------------------------------------------------

    def paintEvent(self, event: QPaintEvent) -> None:
        del event
        painter = QPainter(self)
        try:
            painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
            if not self._sprite.isNull():
                painter.drawPixmap(self.rect(), self._sprite)
        finally:
            painter.end()

    # --- перетаскивание ------------------------------------------------

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_offset = event.globalPosition().toPoint() - self.pos()
            logger.info(
                "ЛКМ нажата: global=%s pos=%s offset=%s",
                event.globalPosition().toPoint(),
                self.pos(),
                self._drag_offset,
            )
            event.accept()

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        if self._drag_offset is not None and event.buttons() & Qt.MouseButton.LeftButton:
            target = event.globalPosition().toPoint() - self._drag_offset
            logger.debug("drag: target=%s (окно сейчас %s)", target, self.pos())
            self.move_clamped(target)
            event.accept()

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            logger.info("ЛКМ отпущена: окно осталось в %s", self.pos())
            self._drag_offset = None

    def move_clamped(self, pos: QPoint) -> None:
        """Переместить окно, зажав координаты в общей рабочей области всех экранов.

        Зажим по объединению экранов, а не по одному: пит может перетаскиваться
        между мониторами (мультимониторная конфигурация dev-стенда).
        """
        area = desktop_area(
            screen.availableGeometry() for screen in QApplication.screens()
        )
        if area.isEmpty():
            primary = self.screen() or QApplication.primaryScreen()
            area = primary.availableGeometry()
        clamped = clamp_to_screen(pos, self.size(), area)
        moved = self.pos()
        self.move(clamped)
        if self.pos() == moved and moved != clamped:
            logger.warning(
                "Wayland/композитор проигнорировал перемещение: хотели %s, осталось %s",
                clamped,
                moved,
            )

    # --- контекстное меню ----------------------------------------------

    def build_menu(self) -> QMenu:
        """Собрать контекстное меню (тестируется отдельно от показа)."""
        menu = QMenu(self)
        menu.addAction("Выход")
        return menu

    def contextMenuEvent(self, event: QContextMenuEvent) -> None:
        menu = self.build_menu()
        chosen = menu.exec(event.globalPos())
        if chosen is not None and chosen.text() == "Выход":
            QApplication.quit()
