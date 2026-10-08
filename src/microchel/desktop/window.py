"""Окно персонажа (PHASE 1): frameless, прозрачное, перетаскиваемое.

PHASE 2: подключает AnimationPlayer — показывает текущий кадр анимации
и подстраивает размер под кадр с сохранением центра (FR-P2.6).
"""

from __future__ import annotations

import logging
from pathlib import Path

from PySide6.QtCore import QPoint, Qt
from PySide6.QtGui import QContextMenuEvent, QMouseEvent, QPainter, QPaintEvent, QPixmap
from PySide6.QtWidgets import QApplication, QMenu, QWidget

from microchel.animation.frames import AnimationClip, ClipLoadError, discover_clip_dirs, load_clip
from microchel.animation.player import AnimationPlayer
from microchel.animation.queue import Priority
from microchel.desktop.geometry import clamp_to_screen, desktop_area

logger = logging.getLogger(__name__)

DEFAULT_SPRITE = (
    Path(__file__).resolve().parents[3] / "assets" / "characters" / "test" / "test_idle.png"
)
DEFAULT_ANIMATION_ROOT = Path(__file__).resolve().parents[3] / "assets" / "characters" / "test"
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

        # PHASE 2: плеер анимаций и текущий кадр (None → рисуем статичный спрайт)
        self._player: AnimationPlayer | None = None
        self._clips: dict[str, AnimationClip] = {}
        self._current_frame: QPixmap | None = None

        self.setWindowTitle("Microchel")
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setMinimumSize(64, 64)
        self.resize(DEFAULT_SIZE, DEFAULT_SIZE)

    # --- анимации (PHASE 2) ----------------------------------------------

    @property
    def player(self) -> AnimationPlayer | None:
        return self._player

    def setup_animation(self, root: Path | None = None) -> bool:
        """Подключить плеер с клипами из root (иерархия Анимация/Состояние/Линия).

        Ищет idle-клип по имени (без учёта регистра) — он играет по умолчанию
        и возвращается после однократных анимаций. Возвращает False, если
        клипов нет (окно остаётся на статичном спрайте).
        """
        root = root or DEFAULT_ANIMATION_ROOT
        clips: dict[str, AnimationClip] = {}
        for clip_dir in discover_clip_dirs(root):
            try:
                clip = load_clip(clip_dir)
            except ClipLoadError as error:
                logger.warning("Клип пропущен: %s", error)
                continue
            clips[clip.name] = clip
        if not clips:
            logger.info("Анимации не найдены в %s — статичный спрайт", root)
            return False

        player = AnimationPlayer(self)
        idle = next(
            (clip for name, clip in clips.items() if "idle" in name.casefold()),
            next(iter(clips.values())),
        )
        player.set_idle(idle)
        player.frame_changed.connect(self._on_frame_changed)
        player.play(idle)
        self._player = player
        self._clips = clips
        logger.info("Анимации подключены: %d клипов, idle=%s", len(clips), idle.name)
        return True

    def play_clip(
        self,
        name_prefix: str,
        *,
        priority: Priority = Priority.BEHAVIOR,
        loop: bool | int = True,
    ) -> bool:
        """Запросить анимацию по префиксу имени (для демо и будущего character)."""
        if self._player is None:
            return False
        for name, clip in self._clips.items():
            if name.startswith(name_prefix):
                self._player.play(clip, priority=priority, loop=loop)
                return True
        logger.warning("Клип не найден по префиксу: %s", name_prefix)
        return False

    def available_clip_names(self) -> list[str]:
        return sorted(self._clips)

    def _on_frame_changed(self, pixmap: QPixmap) -> None:
        """Новый кадр: подстроить размер под кадр с сохранением центра (FR-P2.6)."""
        self._current_frame = pixmap
        frame_size = pixmap.size()
        if frame_size != self.size() and not frame_size.isEmpty():
            center = self.geometry().center()
            self.resize(frame_size)
            top_left = QPoint(
                center.x() - frame_size.width() // 2,
                center.y() - frame_size.height() // 2,
            )
            self.move_clamped(top_left)
        self.update()

    # --- отрисовка -----------------------------------------------------

    def paintEvent(self, event: QPaintEvent) -> None:
        del event
        painter = QPainter(self)
        try:
            painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
            frame = self._current_frame
            if frame is not None and not frame.isNull():
                painter.drawPixmap(self.rect(), frame)
            elif not self._sprite.isNull():
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
