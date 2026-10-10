"""Плеер анимаций (FR-P2.3, FR-P2.4): тайминги из имён кадров, loop, переходы.

Работает в Qt event loop через single-shot QTimer: каждый таймер — конец
текущего кадра; на тике решается: следующий кадр, повтор цикла, прерывание
по pending-запросу (граница кадра) или завершение с выбором из очереди.
"""

from __future__ import annotations

import logging
from pathlib import Path

from PySide6.QtCore import QObject, Qt, QTimer, Signal
from PySide6.QtGui import QPixmap, QTransform

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
        # зеркальные кэпы по пути кадра (mirror="left"): флип дёшев, но на 12 fps
        # и кэше LRU дорог — держим отдельный небольшой словарь
        self._mirror_cache: dict[Path, QPixmap] = {}
        # Переходный клип (MOVED CLIP, PHASE 4): каждая смена анимации начинается
        # с него — цель запоминается в _after_transition и стартует после перехода
        self._transition_clip: AnimationClip | None = None
        self._after_transition: AnimationRequest | None = None
        self._in_transition = False  # сейчас играет переходный клип
        self._last_name: str | None = None  # имя последнего реально запущенного клипа

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
    def is_mirrored(self) -> bool:
        """Текущий запрос играется зеркально (спека mirror = "left")."""
        return self._request.mirror if self._request is not None else False

    @property
    def speed(self) -> float:
        """Текущая скорость (1.0 — норма; 2.0 — вдвое быстрее, 0.5 — медленнее)."""
        return self._request.speed if self._request is not None else 1.0

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

    @property
    def transition(self) -> AnimationClip | None:
        """Установленный переходный клип (MOVED CLIP; None — переход отключён)."""
        return self._transition_clip

    def set_idle(self, clip: AnimationClip | None) -> None:
        """Клип, к которому возвращаемся после однократных анимаций (FR-P2.5)."""
        self._idle_clip = clip

    def set_transition(self, clip: AnimationClip | None) -> None:
        """Переходный клип: каждая смена анимации начинается с него (MOVED CLIP).

        Первый старт после set_transition/stop играется без перехода; переход
        не эмитит animation_finished (иначе controller принял бы его за конец
        реакции и перезапустил бы клип состояния поверх цели).
        """
        self._transition_clip = clip

    # --- управление ------------------------------------------------------

    def play(
        self,
        clip: AnimationClip,
        *,
        priority: Priority = Priority.IDLE,
        loop: bool | int = True,
        restart: bool = False,
        mirror: bool = False,
        speed: float = 1.0,
    ) -> None:
        """Запросить анимацию (FR-P2.3, FR-P2.4, FR-P2.5).

        - Ничего не играет — начать сразу.
        - Приоритет выше текущего — прервать на границе кадра (pending).
        - Равный приоритет и уже играет этот же клип — без действия (restart=True принудительно).
        - Равный/ниже приоритет — в очередь FIFO.
        - restart=True — немедленная замена текущего запроса (другой клип тоже);
          так FSM меняет looping-состояния без застревания в очереди (PHASE 3).
        - mirror=True — кадры показываются зеркально по X (спека mirror="left", PHASE 4).
        - speed — множитель скорости: длительность кадра делится на speed
          (2.0 — вдвое быстрее, 0.5 — вдвое медленнее; PHASE 4, --speed).
        """
        request = AnimationRequest(
            clip=clip,
            priority=priority,
            loop=loop,
            restart=restart,
            mirror=mirror,
            speed=max(0.01, float(speed)),
        )
        if self._clip is None or self._request is None:
            self._start(request)
            return
        same_clip = clip.name == self._request.clip.name and mirror == self._request.mirror
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
        self._after_transition = None
        self._in_transition = False
        self._last_name = None

    # --- внутренняя механика ---------------------------------------------

    def _start(self, request: AnimationRequest) -> None:
        """Запустить запрос; при смене анимации — сначала переходный клип."""
        self._after_transition = None  # новая цель по умолчанию
        if (
            self._transition_clip is not None
            and not self._in_transition
            # переход только при смене: первый старт (_last_name is None) — без него
            and self._last_name is not None
            and request.clip.name != self._last_name
            and request.clip.name != self._transition_clip.name
        ):
            # смена анимации: играем переход, цель — после его завершения
            self._after_transition = request
            logger.debug(
                "Смена анимации: сначала переход %s, затем %s",
                self._transition_clip.name,
                request.clip.name,
            )
            request = AnimationRequest(
                clip=self._transition_clip,
                priority=request.priority,
                loop=False,
                restart=True,
                speed=request.speed,
            )
        self._start_unchecked(request)

    def _start_unchecked(self, request: AnimationRequest) -> None:
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
        transition = self._transition_clip
        self._in_transition = transition is not None and request.clip.name == transition.name
        self._last_name = request.clip.name

    def _show_current(self) -> None:
        if self._clip is None:
            return
        frame = self._clip.frames[self._cursor]
        try:
            pixmap = self._cache.load(frame.path)
        except ValueError:
            logger.error("Кадр не загрузился, останов: %s", frame.path)
            self.stop()
            return
        if self._request is not None and self._request.mirror:
            pixmap = self._mirrored(frame.path, pixmap)
        self._frame_pixmap = pixmap
        self.frame_changed.emit(pixmap)

    def _mirrored(self, path: Path, pixmap: QPixmap) -> QPixmap:
        """Зеркальный кадр (по X) с точным пикселем — FastTransformation."""
        cached = self._mirror_cache.get(path)
        if cached is None:
            cached = pixmap.transformed(
                QTransform().scale(-1, 1), Qt.TransformationMode.FastTransformation
            )
            self._mirror_cache[path] = cached
        return cached

    def _schedule(self) -> None:
        if self._clip is None:
            return
        duration = self._clip.frames[self._cursor].duration_ms
        speed = self.speed
        self._timer.start(max(1, int(round(duration / speed))))

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
        transition = self._transition_clip
        if (
            transition is not None
            and self._after_transition is not None
            and finished_name == transition.name
        ):
            # переход отыгран — запускаем запомненную цель (без animation_finished,
            # иначе controller принял бы конец перехода за конец реакции)
            target, self._after_transition = self._after_transition, None
            self._start(target)
            return
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
