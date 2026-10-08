"""Плеер анимаций (FR-P2.3, FR-P2.4): тайминги из имён кадров, loop, переходы.

Работает в Qt event loop через single-shot QTimer: каждый таймер — конец
текущего кадра; на тике решается: следующий кадр, повтор цикла, прерывание
по pending-запросу (граница кадра) или завершение с выбором из очереди.
"""

from __future__ import annotations

import logging
from pathlib import Path

from PySide6.QtCore import QObject, QTimer, Signal
from PySide6.QtGui import QPixmap

from microchel.animation.cache import FrameCache
from microchel.animation.frames import AnimationClip
from microchel.animation.queue import AnimationQueue, AnimationRequest, Priority

logger = logging.getLogger(__name__)


def load_pixmap(path: Path) -> tuple[QPixmap, int]:
    """Загрузчик для кэша: путь → (QPixmap, размер в байтах)."""
    pixmap = QPixmap(str(path))
    if pixmap.isNull():
        raise ValueError(f"не удалось загрузить кадр: {path}")
    size_bytes = pixmap.width() * pixmap.height() * (pixmap.depth() // 8)
    return pixmap, size_bytes


class AnimationPlayer(QObject):
    """Проигрывает клипы, переключается по приоритетам, кэширует кадры."""

    frame_changed = Signal(object)  # QPixmap — новый текущий кадр
    animation_started = Signal(str)  # name клипа
    animation_finished = Signal(str)  # name клипа (natural end, не прерывание)

    def __init__(
        self,
        parent: QObject | None = None,
        *,
        cache_max_bytes: int = 64 * 1024 * 1024,
        cache: FrameCache[QPixmap] | None = None,
    ) -> None:
        super().__init__(parent)
        self._cache: FrameCache[QPixmap] = cache or FrameCache(cache_max_bytes, load_pixmap)
        self._queue = AnimationQueue()
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self._advance)

        self._clip: AnimationClip | None = None
        self._request: AnimationRequest | None = None
        self._cursor = 0
        self._loop_left: int | None = None  # None = бесконечный loop
        self._idle_clip: AnimationClip | None = None
        self._pending: AnimationRequest | None = None  # ждёт границы кадра
        self._frame_pixmap: QPixmap | None = None

    # --- состояние -------------------------------------------------------

    @property
    def current_clip(self) -> AnimationClip | None:
        return self._clip

    @property
    def current_priority(self) -> Priority | None:
        return self._request.priority if self._request else None

    @property
    def frame_index(self) -> int:
        return self._cursor

    @property
    def is_playing(self) -> bool:
        return self._clip is not None and self._timer.isActive()

    @property
    def frame_pixmap(self) -> QPixmap | None:
        """Текущий показанный кадр (для отрисовки окном)."""
        return self._frame_pixmap

    @property
    def cache(self) -> FrameCache[QPixmap]:
        return self._cache

    @property
    def pending(self) -> AnimationRequest | None:
        return self._pending

    def set_idle(self, clip: AnimationClip | None) -> None:
        """Клип, к которому возвращаемся после однократных анимаций (FR-P2.5)."""
        self._idle_clip = clip

    # --- управление ------------------------------------------------------

    def play(
        self,
        clip: AnimationClip,
        *,
        priority: Priority = Priority.IDLE,
        loop: bool | int = True,
        restart: bool = False,
    ) -> None:
        """Запросить анимацию (FR-P2.3, FR-P2.4, FR-P2.5).

        - Ничего не играет — начать сразу.
        - Приоритет выше текущего — прервать на границе кадра (pending).
        - Равный приоритет и уже играет этот же клип — без действия (restart=True принудительно).
        - Равный/ниже приоритет — в очередь FIFO.
        - restart=True — немедленная замена текущего запроса (другой клип тоже);
          так FSM меняет looping-состояния без застревания в очереди (PHASE 3).
        """
        request = AnimationRequest(clip=clip, priority=priority, loop=loop, restart=restart)
        if self._clip is None or self._request is None:
            self._start(request)
            return
        same_clip = clip.name == self._request.clip.name
        if same_clip and not restart and priority <= self._request.priority:
            return  # уже играет — не перезапускаем (FR-P2.4)
        if restart:
            self._start(request)  # принудительная замена — немедленно (PHASE 3: смена состояний)
            return
        if priority > self._request.priority:
            self._pending = request  # прерывание на границе кадра
            return
        self._queue.push(request)

    def stop(self) -> None:
        """Полная остановка: таймер, очередь, pending — всё сбрасывается."""
        self._timer.stop()
        self._clip = None
        self._request = None
        self._pending = None
        self._queue.clear()

    # --- внутренняя механика ---------------------------------------------

    def _start(self, request: AnimationRequest) -> None:
        self._timer.stop()
        self._clip = request.clip
        self._request = request
        self._cursor = 0
        if request.loop is True:
            self._loop_left = None
        else:
            self._loop_left = 1 if request.loop is False else max(1, int(request.loop))
        self._pending = None
        logger.debug(
            "Анимация начата: %s (priority=%s, loop=%s)",
            request.clip.name,
            request.priority.name,
            request.loop,
        )
        self.animation_started.emit(request.clip.name)
        self._show_current()
        self._schedule()

    def _show_current(self) -> None:
        if self._clip is None:
            return
        frame = self._clip.frames[self._cursor]
        try:
            self._frame_pixmap = self._cache.load(frame.path)
        except ValueError:
            logger.error("Кадр не загрузился, останов: %s", frame.path)
            self.stop()
            return
        self.frame_changed.emit(self._frame_pixmap)

    def _schedule(self) -> None:
        if self._clip is None:
            return
        duration = self._clip.frames[self._cursor].duration_ms
        self._timer.start(max(1, duration))

    def _advance(self) -> None:
        """Таймер кончился: прерывание → следующий кадр → повтор → завершение."""
        if self._pending is not None:
            request, self._pending = self._pending, None
            self._start(request)
            return
        if self._clip is None:
            return
        next_cursor = self._cursor + 1
        if next_cursor < len(self._clip.frames):
            self._cursor = next_cursor
            self._show_current()
            self._schedule()
            return
        # конец прохода по клипу
        if self._loop_left is None or self._loop_left > 1:
            if self._loop_left is not None:
                self._loop_left -= 1
            self._cursor = 0
            self._show_current()
            self._schedule()
            return
        # клип завершён (natural end)
        finished_name = self._clip.name
        self._timer.stop()
        self._clip = None
        self._request = None
        self._loop_left = None
        self.animation_finished.emit(finished_name)
        self._start_next()

    def _start_next(self) -> None:
        """После завершения: очередь по приоритетам, иначе idle (FR-P2.5)."""
        request = self._queue.pop_best()
        if request is not None:
            self._start(request)
            return
        if self._clip is not None:
            # слушатель animation_finished уже запустил новую анимацию (PHASE 3)
            return
        if self._idle_clip is not None:
            self._start(AnimationRequest(clip=self._idle_clip, priority=Priority.IDLE, loop=True))
            return
        logger.debug("Плеер простаивает: нет ни очереди, ни idle-клипа")
