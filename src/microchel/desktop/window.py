"""Окно персонажа (PHASE 1): frameless, прозрачное, перетаскиваемое.

PHASE 2: подключает AnimationPlayer — показывает кадры анимации на
фиксированном холсте (максимум кадров всех клипов), без покадрового ресайза (FR-P2.6).
"""

from __future__ import annotations

import logging
from collections.abc import Mapping, Sequence
from pathlib import Path

from PySide6.QtCore import QPoint, QRect, QSize, QSizeF, Qt
from PySide6.QtGui import (
    QColor,
    QContextMenuEvent,
    QFont,
    QImage,
    QImageReader,
    QMouseEvent,
    QPainter,
    QPaintEvent,
    QPen,
    QPixmap,
)
from PySide6.QtWidgets import QApplication, QMenu, QWidget

from microchel.animation.frames import AnimationClip, ClipLoadError, discover_clip_dirs, load_clip
from microchel.animation.player import AnimationPlayer
from microchel.animation.queue import Priority
from microchel.animation.spec import ClipSpec, load_clip_specs
from microchel.common.event_bus import EventBus
from microchel.common.events import UserEvent, UserEventKind
from microchel.desktop.geometry import clamp_to_screen, desktop_area

logger = logging.getLogger(__name__)

CHARACTERS_ROOT = Path(__file__).resolve().parents[3] / "assets" / "characters"
DEFAULT_ANIMATION_ROOT = CHARACTERS_ROOT / "malinka"
# спрайт-фоллбэк, пока анимации не подключены: первый кадр приветствия
DEFAULT_SPRITE = DEFAULT_ANIMATION_ROOT / "Welcome" / "Greeting" / "1" / "_000_150.png"
DEFAULT_SIZE = 160
DEFAULT_PET_SCALE = 0.65  # масштаб персонажа: эталонная высота 458 → окно ~298
DRAG_THRESHOLD_PX = 5  # смещение ЛКМ ≥ порога — это уже драг, не клик (FR-P3.5)


def _alpha_bbox(image: QImage) -> QRect:
    """Tight bbox непрозрачных пикселей изображения (анализатор модели).

    Поля прозрачности вокруг спрайта различаются от кадра к кадру — bbox
    показывает, где модель реально находится внутри кадра. Построчный скан
    альфа-канала (strip по 0x00) — быстро и без внешних зависимостей.
    """
    img = image.convertToFormat(QImage.Format.Format_ARGB32)
    width, height = img.width(), img.height()
    if width == 0 or height == 0:
        return QRect()
    data = bytes(img.constBits())
    stride = img.bytesPerLine()
    top = bottom = left = right = -1
    for y in range(height):
        alphas = data[y * stride : y * stride + width * 4][3::4]
        core = alphas.strip(b"\x00")
        if not core:
            continue
        x0 = len(alphas) - len(alphas.lstrip(b"\x00"))
        x1 = x0 + len(core) - 1
        if top < 0:
            top = y
        bottom = y
        left = x0 if left < 0 or x0 < left else left
        right = x1 if x1 > right else right
    if top < 0:
        return QRect()
    return QRect(left, top, right - left + 1, bottom - top + 1)


class PetWindow(QWidget):
    """Прозрачное окно с перетаскиванием; спрайт-фоллбэк — первый кадр приветствия."""

    def __init__(
        self,
        sprite_path: Path | None = None,
        parent: QWidget | None = None,
        *,
        bus: EventBus | None = None,
        frame_stats: bool = False,
    ) -> None:
        super().__init__(parent)
        self._drag_offset: QPoint | None = None
        self._press_pos: QPoint | None = None  # глобальная позиция ЛКМ при нажатии
        self._dragged = False  # был ли драг от порога до отпускания
        self._bus = bus
        self._sprite_path = sprite_path or DEFAULT_SPRITE
        self._sprite = QPixmap(str(self._sprite_path))
        if self._sprite.isNull():
            logger.warning("Спрайт-фоллбэк не загружен: %s", self._sprite_path)

        # PHASE 2: плеер анимаций и текущий кадр (None → рисуем статичный спрайт)
        self._player: AnimationPlayer | None = None
        self._clips: dict[str, AnimationClip] = {}
        self._current_frame: QPixmap | None = None
        self._root: Path = DEFAULT_ANIMATION_ROOT
        self._specs: dict[str, ClipSpec] = {}  # playback-спека (clips.toml)
        self._character: str = DEFAULT_ANIMATION_ROOT.name
        # PHASE 4: масштаб персонажа и скорость анимаций.
        # Кадры сменяются без кроссфейда (решение пользователя): плеер играет
        # «в лоб», полупрозрачность/рябь при быстрой смене кадров недопустимы.
        self._pet_scale = DEFAULT_PET_SCALE
        # масштаб текущего клипа из clips.toml (нормализация размера анимаций)
        self._clip_scale = 1.0
        self._speed = 1.0
        # фиксированный холст окна: макс. размер отрисовки при pet-scale=1 (FR-P2.6)
        self._footprint = QSizeF(DEFAULT_SIZE, DEFAULT_SIZE)
        # переходный клип при смене анимации (MOVED CLIP); showcase выключает
        self._transition_enabled = True
        # фоновая idle между анимациями; showcase выключает (слот без фона)
        self._idle_fallback = True
        # анализатор модели (--show-frame-stats): bbox и размеры на каждом кадре
        self._frame_stats = frame_stats
        self._stats_bbox: QRect | None = None
        self._stats_frame_no: int | None = None
        # bbox модели по cacheKey кадра (якорь отрисовки + анализатор)
        self._bbox_cache: dict[int, QRect] = {}

        self.setWindowTitle("Microchel")
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setMinimumSize(64, 64)
        self._footprint = self._sprite_footprint()
        self._apply_window_size()

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
        self._root = root
        self._specs = load_clip_specs(root / "clips.toml")
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
            self._footprint = self._sprite_footprint()
            self._apply_window_size()
            return False

        if self._player is not None:
            # повторное подключение (смена персонажа): останавливаем старый плеер,
            # иначе его таймер продолжит показывать кадры прежнего персонажа
            self._player.stop()
            self._player.frame_changed.disconnect(self._on_frame_changed)
            self._player.animation_started.disconnect(self._on_animation_started)
            self._player.deleteLater()
        self._current_frame = None
        self._clip_scale = 1.0
        self._clips = clips
        self._footprint = self._compute_footprint()
        self._apply_window_size()

        player = AnimationPlayer(self)
        idle = next(
            (clip for name, clip in clips.items() if "idle" in name.casefold()),
            next(iter(clips.values())),
        )
        player.set_idle(idle if self._idle_fallback else None)
        transition = clips.get("Move/Transition")
        if transition is not None and self._transition_enabled:
            # каждая смена анимации начинается с переходного клипа (MOVED CLIP)
            player.set_transition(transition)
        player.frame_changed.connect(self._on_frame_changed)
        player.animation_started.connect(self._on_animation_started)
        player.play(idle)
        self._player = player
        self._character = root.name
        logger.info(
            "Анимации подключены: персонаж %s, %d клипов, idle=%s",
            root.name,
            len(clips),
            idle.name,
        )
        return True

    def _sprite_footprint(self) -> QSizeF:
        """Холст без клипов: спрайт-фоллбэк, масштаб клипа 1.0."""
        if self._sprite.isNull():
            return QSizeF(DEFAULT_SIZE, DEFAULT_SIZE)
        return QSizeF(self._sprite.size())

    def _compute_footprint(self) -> QSizeF:
        """Максимальный размер отрисовки клипов при pet-scale=1 (FR-P2.6).

        Размеры кадров снимаются QImageReader'ом по заголовку PNG — без
        декодирования. Холст учитывает масштаб каждого клипа (clips.toml):
        фиксированному окну хватает на самый крупный кадр любого клипа.
        """
        if self._sprite.isNull():
            width, height = 1.0, 1.0
        else:
            width, height = float(self._sprite.width()), float(self._sprite.height())
        for name, clip in self._clips.items():
            spec = self._specs.get(name)
            factor = spec.scale if spec is not None and spec.scale is not None else 1.0
            for frame in clip.frames:
                size = self._frame_size(frame.path)
                if size is None:
                    logger.warning("Размер кадра не прочитан: %s", frame.path)
                    continue
                width = max(width, size.width() * factor)
                height = max(height, size.height() * factor)
        return QSizeF(width, height)

    @staticmethod
    def _frame_size(path: Path) -> QSize | None:
        """Размер кадра по заголовку файла; None — прочитать не удалось."""
        size = QImageReader(str(path)).size()
        return None if size.isEmpty() else size

    def _window_size(self) -> QSize:
        """Размер окна: фиксированный холст × pet-scale (минимум 1 px по стороне)."""
        return QSize(
            max(1, int(round(self._footprint.width() * self._pet_scale))),
            max(1, int(round(self._footprint.height() * self._pet_scale))),
        )

    def _apply_window_size(self) -> None:
        """Ресайз окна под холст, якорь — низ-центр (ноги персонажа на месте).

        Единственное место, меняющее размер окна (FR-P2.6): покадровый ресайз
        дёргал геометрию и растягивал кадры — окно дрожало, а кадры меняли
        масштаб. Ресайз редкий (setup, set_pet_scale, смена персонажа), поэтому
        синхронный repaint() больше не нужен.
        """
        target = self._window_size()
        if target == self.size():
            return
        geometry = self.geometry()
        self.resize(target)
        actual = self.size()  # setMinimumSize может дать больше target
        # якорь низ-центр: центр по формуле QRect.center() (x + (w-1)//2) — без дрейфа 1 px
        top_left = QPoint(
            geometry.x() + (geometry.width() - 1) // 2 - (actual.width() - 1) // 2,
            geometry.bottom() - actual.height() + 1,
        )
        self.move_clamped(top_left)
        self.update()
        logger.info(
            "Окно %dx%d: холст %.0fx%.0f, pet-scale %.2f",
            actual.width(),
            actual.height(),
            self._footprint.width(),
            self._footprint.height(),
            self._pet_scale,
        )

    def play_clip(
        self,
        name_prefix: str,
        *,
        priority: Priority = Priority.BEHAVIOR,
        loop: bool | int = True,
        restart: bool = False,
        frame_indices: Sequence[int] | None = None,
        mirror: bool = False,
    ) -> bool:
        """Запросить анимацию по префиксу имени (демо, character, showcase, тесты).

        frame_indices — показать только эти кадры клипа в заданном порядке
        (план playback-спеки: сегмент loop с повторами); такой план всегда
        играется одним проходом (loop принудительно False). mirror — показ
        кадров зеркально по X (spec.mirror = "left").
        """
        if self._player is None:
            return False
        for name, clip in self._clips.items():
            if name.startswith(name_prefix):
                if frame_indices is not None:
                    planned = self._plan_clip(clip, frame_indices)
                    if planned is None:
                        return False
                    clip = planned
                    loop = False
                self._player.play(
                    clip,
                    priority=priority,
                    loop=loop,
                    restart=restart,
                    mirror=mirror,
                    speed=self._speed,
                )
                return True
        logger.warning("Клип не найден по префиксу: %s", name_prefix)
        return False

    @staticmethod
    def _plan_clip(clip: AnimationClip, frame_indices: Sequence[int]) -> AnimationClip | None:
        """Производный клип по плану: кадры исходного в заданном порядке.

        Полный диапазон без повторов → исходный клип (имя и логи не меняем).
        Пустой план или индексы вне границ — None (запрос отклоняется).
        """
        count = len(clip.frames)
        full = tuple(range(count))
        indices = tuple(frame_indices)
        if indices == full:
            return clip
        if not indices:
            logger.warning("План клипа %s пуст — запрос отклонён", clip.name)
            return None
        bad = next((index for index in indices if index < 0 or index >= count), None)
        if bad is not None:
            logger.warning(
                "План клипа %s: индекс %s вне [0, %d) — запрос отклонён",
                clip.name,
                bad,
                count,
            )
            return None
        return AnimationClip(
            name=f"{clip.name}#plan",
            line=clip.line,
            frames=tuple(clip.frames[index] for index in indices),
        )

    def clip_durations(self, name_prefix: str) -> tuple[int, ...] | None:
        """Длительности кадров клипа (мс) по порядку индексов; None — нет клипа."""
        for name, clip in self._clips.items():
            if name.startswith(name_prefix):
                return tuple(frame.duration_ms for frame in clip.frames)
        return None

    @property
    def clip_specs(self) -> Mapping[str, ClipSpec]:
        """Playback-спека текущего персонажа (clips.toml; пусто — без уточнений)."""
        return self._specs

    @property
    def character_root(self) -> Path:
        """Каталог ассетов текущего персонажа (для clips.toml и ресурсов)."""
        return self._root

    def available_clip_names(self) -> list[str]:
        return sorted(self._clips)

    def available_characters(self) -> list[str]:
        """Имена доступных персонажей — каталоги в assets/characters/ (PHASE 4)."""
        if not CHARACTERS_ROOT.is_dir():
            return []
        return sorted(entry.name for entry in CHARACTERS_ROOT.iterdir() if entry.is_dir())

    @property
    def character(self) -> str:
        """Имя текущего персонажа (каталог с ассетами)."""
        return self._character

    @property
    def pet_scale(self) -> float:
        """Масштаб персонажа на экране (1.0 — натуральный размер кадра)."""
        return self._pet_scale

    @property
    def clip_scale(self) -> float:
        """Масштаб текущего клипа из clips.toml (1.0 — без нормализации)."""
        return self._clip_scale

    @property
    def animation_speed(self) -> float:
        """Глобальная скорость анимаций (1.0 — норма; 0.5 — вдвое медленнее)."""
        return self._speed

    def set_pet_scale(self, scale: float) -> None:
        """Масштаб персонажа: холст = footprint × scale, якорь низ-центр (PHASE 4).

        Единственный ресайз окна в рантайме (плюс setup/смена персонажа);
        рендер масштабируется билинейно (SmoothPixmapTransform). Невалидное
        значение отклоняется.
        """
        value = float(scale)
        if value <= 0:
            logger.warning("pet-scale=%r не положительное — отклонено", scale)
            return
        self._pet_scale = value
        self._apply_window_size()
        logger.info("Масштаб персонажа: %.2f", value)

    def set_animation_speed(self, speed: float) -> None:
        """Глобальная скорость анимаций: 1 — норма, 0.5 — вдвое медленнее (PHASE 4)."""
        value = float(speed)
        if value <= 0:
            logger.warning("speed=%r не положительное — отклонено", speed)
            return
        self._speed = value
        logger.info("Скорость анимаций: %.2f", value)

    def set_transition_enabled(self, enabled: bool) -> None:
        """Переходный клип (MOVED CLIP) при смене анимации: вкл/выкл.

        Showcase выключает его: Move/Transition показывается отдельным слотом
        цикла, а не вставляется перед каждым клипом. Переживает смену
        персонажа — setup_animation пересоздаёт плеер и учитывает флаг.
        """
        value = bool(enabled)
        if value == self._transition_enabled:
            return
        self._transition_enabled = value
        if self._player is not None:
            self._player.set_transition(self._clips.get("Move/Transition") if value else None)
        logger.debug("Переходный клип (MOVED CLIP): %s", "включён" if value else "отключён")

    def set_idle_fallback_enabled(self, enabled: bool) -> None:
        """Фоновая idle между анимациями: вкл/выкл.

        Showcase выключает её: в паузах между слотами держится последний кадр
        показанного клипа (инспекция без фоновой анимации; «кадры idle до 6»
        в паузе 1 с — это была фоновая Idle/Normal). Переживает смену
        персонажа — setup_animation пересоздаёт плеер и учитывает флаг.
        """
        value = bool(enabled)
        if value == self._idle_fallback:
            return
        self._idle_fallback = value
        if self._player is not None and self._clips:
            idle = next(
                (clip for name, clip in self._clips.items() if "idle" in name.casefold()),
                next(iter(self._clips.values())),
            )
            self._player.set_idle(idle if value else None)
        logger.debug("Фоновая idle: %s", "включена" if value else "отключена")

    def switch_character(self, name: str) -> bool:
        """Переключить персонажа по имени каталога (контекстное меню).

        False — каталог не найден или в нём нет клипов; текущий не меняется.
        """
        root = CHARACTERS_ROOT / name
        if not root.is_dir():
            logger.warning("Персонаж не найден: %s", root)
            return False
        return self.setup_animation(root)

    def _on_animation_started(self, name: str) -> None:
        """Смена клипа: применить его масштаб из clips.toml (.clips/#plan-суффикс).

        Окно не пересчитываем никогда: холст фиксирован под максимальный кадр
        (см. _compute_footprint). Покадровый и поклиповый ресайз — источник
        дрожания и чёрных мигов на границе анимации.
        """
        clip_name = name.split("#", 1)[0]
        spec = self._specs.get(clip_name)
        scale = spec.scale if spec is not None and spec.scale is not None else 1.0
        if scale == self._clip_scale:
            return
        self._clip_scale = scale
        logger.debug("Клип %s: масштаб %.3f", clip_name, scale)

    def _on_frame_changed(self, pixmap: QPixmap) -> None:
        """Новый кадр: только перерисовать — окно фиксированного размера.

        Покадровый ресайз убран (FR-P2.6): он дёргал геометрию и растягивал
        кадры под окно — источник дрожания и чёрных мигов на границе анимации.
        """
        self._current_frame = pixmap
        if self._frame_stats and self._player is not None:
            self._stats_frame_no = self._player.frame_index
        self.update()

    def _scaled_size(self, size: QSize) -> QSize:
        """Размер кадра с учётом pet-scale × масштаба клипа (минимум 1 px по стороне)."""
        factor = self._pet_scale * self._clip_scale
        return QSize(
            max(1, int(round(size.width() * factor))),
            max(1, int(round(size.height() * factor))),
        )

    # --- отрисовка -----------------------------------------------------

    def paintEvent(self, event: QPaintEvent) -> None:
        """Кадр в расчётном размере, якорь — низ-центр модели; окно не растягивает.

        Растяжение в self.rect() превращало разную высоту кадров (262–419 px)
        в дёрганье масштаба — кадр рисуется в точном размере
        round(canvas × pet-scale × clip-scale). Якорь по bbox модели (а не по
        канвасу) держит ноги на земле и центр на месте: у морфинг-клипов
        модель гуляет внутри канваса (Move: центр-x ±24 px, низ 0–10 px).
        """
        del event
        painter = QPainter(self)
        try:
            painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
            frame = self._current_frame
            if frame is None or frame.isNull():
                frame = self._sprite
            if frame is None or frame.isNull():
                return
            draw_size = self._scaled_size(frame.size())
            bbox = self._model_bbox(frame)
            # якорь — низ-центр МОДЕЛИ (не канваса): канвас сдвигается так,
            # чтобы bbox модели встал в низ-центр окна — ноги на земле,
            # центр на месте; пустой кадр — прежний якорь низ-центром канваса
            if bbox.isNull():
                dx = dy = 0
            else:
                sx = draw_size.width() / frame.width()
                sy = draw_size.height() / frame.height()
                dx = round((frame.width() / 2 - (bbox.x() + bbox.width() / 2)) * sx)
                dy = round((frame.height() - (bbox.y() + bbox.height())) * sy)
            target = QRect(
                (self.width() - draw_size.width()) // 2 + dx,
                self.height() - draw_size.height() + dy,
                draw_size.width(),
                draw_size.height(),
            )
            painter.drawPixmap(target, frame)
            if self._frame_stats:
                self._draw_frame_stats(painter, frame, target)
        finally:
            painter.end()

    def _model_bbox(self, frame: QPixmap) -> QRect:
        """Bbox модели кадра (непрозрачные пиксели) с кэшем по cacheKey.

        Один расчёт на кадр: якорь отрисовки и анализатор (--show-frame-stats)
        используют один и тот же bbox. Зеркальный кадр — свой cacheKey.
        """
        key = frame.cacheKey()
        bbox = self._bbox_cache.get(key)
        if bbox is None:
            bbox = _alpha_bbox(frame.toImage())
            if len(self._bbox_cache) > 512:
                self._bbox_cache.clear()
            self._bbox_cache[key] = bbox
        return bbox

    def _draw_frame_stats(self, painter: QPainter, frame: QPixmap, target: QRect) -> None:
        """Анализатор модели: bbox модели, границы кадра и размеры (--show-frame-stats).

        Красный прямоугольник — bbox непрозрачных пикселей модели, голубой —
        границы кадра, зелёная линия — «земля» (низ окна). Текст показывает
        размеры модели и кадра в пикселях отрисовки и оба масштаба.
        """
        bbox = self._model_bbox(frame)
        self._stats_bbox = bbox
        # bbox модели в координатах отрисованного кадра (пропорционально)
        sx = target.width() / frame.width()
        sy = target.height() / frame.height()
        model = (
            QRect(
                target.x() + round(bbox.x() * sx),
                target.y() + round(bbox.y() * sy),
                round(bbox.width() * sx),
                round(bbox.height() * sy),
            )
            if not bbox.isNull()
            else QRect()
        )

        painter.save()
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.setPen(QPen(QColor(120, 190, 255, 200), 1))
        painter.drawRect(target.adjusted(0, 0, -1, -1))
        if not model.isNull():
            painter.setPen(QPen(QColor(255, 80, 80), 2))
            painter.drawRect(model.adjusted(0, 0, -1, -1))
        painter.setPen(QPen(QColor(80, 220, 80, 200), 1))
        painter.drawLine(0, self.height() - 1, self.width() - 1, self.height() - 1)

        font = QFont()
        font.setPixelSize(11)
        painter.setFont(font)
        player = self._player
        clip = player.current_clip if player is not None else None
        name = clip.name.split("#", 1)[0] if clip is not None else "спрайт"
        frame_no = self._stats_frame_no if self._stats_frame_no is not None else "-"
        lines = [
            f"{name} #{frame_no}",
            f"модель {model.width()}x{model.height()}",
            f"кадр {frame.width()}x{frame.height()}",
            f"c{self._clip_scale:.2f} p{self._pet_scale:.2f}",
        ]
        metrics = painter.fontMetrics()
        text_w = max(metrics.horizontalAdvance(line) for line in lines)
        painter.fillRect(0, 0, text_w + 8, metrics.height() * len(lines) + 6, QColor(0, 0, 0, 150))
        painter.setPen(QPen(QColor(255, 255, 255)))
        for index, line in enumerate(lines):
            painter.drawText(4, metrics.height() * (index + 1) + 1, line)
        painter.restore()

    # --- перетаскивание ------------------------------------------------

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_offset = event.globalPosition().toPoint() - self.pos()
            self._press_pos = event.globalPosition().toPoint()
            self._dragged = False
            logger.info(
                "ЛКМ нажата: global=%s pos=%s offset=%s",
                event.globalPosition().toPoint(),
                self.pos(),
                self._drag_offset,
            )
            event.accept()

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        if self._drag_offset is not None and event.buttons() & Qt.MouseButton.LeftButton:
            if not self._dragged and self._press_pos is not None:
                delta = event.globalPosition().toPoint() - self._press_pos
                if delta.manhattanLength() >= DRAG_THRESHOLD_PX:
                    self._dragged = True
                    self._emit_user_event(UserEventKind.DRAG_START)
            target = event.globalPosition().toPoint() - self._drag_offset
            logger.debug("drag: target=%s (окно сейчас %s)", target, self.pos())
            self.move_clamped(target)
            event.accept()

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            logger.info("ЛКМ отпущена: окно осталось в %s", self.pos())
            if self._dragged:
                self._emit_user_event(UserEventKind.DRAG_END)
            elif self._press_pos is not None:
                delta = event.globalPosition().toPoint() - self._press_pos
                if delta.manhattanLength() < DRAG_THRESHOLD_PX:
                    self._emit_user_event(UserEventKind.CLICK)
            self._drag_offset = None
            self._press_pos = None
            self._dragged = False

    def move_clamped(self, pos: QPoint) -> None:
        """Переместить окно, зажав координаты в общей рабочей области всех экранов.

        Зажим по объединению экранов, а не по одному: пит может перетаскиваться
        между мониторами (мультимониторная конфигурация dev-стенда).
        """
        area = desktop_area(screen.availableGeometry() for screen in QApplication.screens())
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

    def move_by(self, dx: int) -> bool:
        """Сдвиг по X для ходьбы (FR-P3.4): True — позиция реально изменилась."""
        before = self.pos()
        self.move_clamped(before + QPoint(dx, 0))
        return self.pos() != before

    def _emit_user_event(self, kind: UserEventKind) -> None:
        """Отправить событие пользователя в шину (FR-P3.5); без шины — no-op."""
        if self._bus is None:
            return
        logger.info("Событие пользователя: %s", kind.value)
        self._bus.emit(UserEvent(kind=kind))

    # --- контекстное меню ----------------------------------------------

    def build_menu(self) -> QMenu:
        """Собрать контекстное меню (тестируется отдельно от показа)."""
        menu = QMenu(self)
        names = self.available_characters()
        if len(names) > 1:
            submenu = menu.addMenu("Персонаж")
            for name in names:
                action = submenu.addAction(name)
                action.setCheckable(True)
                action.setChecked(name == self._character)
                action.setData(name)
        menu.addAction("Выход")
        return menu

    def contextMenuEvent(self, event: QContextMenuEvent) -> None:
        menu = self.build_menu()
        chosen = menu.exec(event.globalPos())
        if chosen is None:
            return
        if chosen.text() == "Выход":
            QApplication.quit()
            return
        name = chosen.data()
        if isinstance(name, str) and self.switch_character(name):
            logger.info("Персонаж переключён: %s", name)
