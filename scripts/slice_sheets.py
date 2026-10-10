"""Нарезка шитов девочки-малинки → assets/characters/malinka/ (PHASE 4).

Алгоритм — масочная нарезка с явной принадлежностью пикселей кадрам:

1. Сегментация по alpha-маске: связные компоненты (8-связность), ряды шита —
   пустые промежутки проекции по Y. Кадр — спрайт-компонент (группировка
   частей к силуэту): AUTO находит спрайты по маске и колонки по их центрам,
   GRID задаёт равномерную сетку, MANUAL — явные границы колонок.
2. Принадлежность: каждый компонент целиком достаётся своему кадру —
   кроссоверы заходят в соседние ячейки, но не режутся. Компонент «слитых
   кадров» (пиксельно соединённые персонажи, масса в двух слотах) в AUTO —
   ошибка диагностики с кандидатами разделителей, в GRID/MANUAL —
   контролируемый разрез по границе с предупреждением. Мусор
   (< MIN_COMPONENT_PX) и мелкие эффекты пишутся кадру ближайшего спрайта;
   полупрозрачная кайма (< ALPHA_STRUCT, не глубже 2 px от структуры)
   привязывается к компоненту. Все пиксели оригинала сохраняются 1:1
   (включая мягкие края), PNG не масштабируются.
3. Извлечение: в PNG кадра попадают ТОЛЬКО пиксели его компонентов —
   прямоугольный кроп не используется, чужие пиксели внутри bbox исключаются.
4. Стабильная привязка: кадр кладётся на холст относительно СЛОТА сетки
   (не собственного bbox) — движение сохраняется как нарисовано, дёрганья
   между кадрами нет; пол канвы — низ ряда.
5. Валидация: expect (ожидаемое число ячеек), пропуски ячеек, отклонение
   кадра от слота, аномалии размеров; невозможная принадлежность — ошибка
   диагностики, а не тихая порча. Диагностический PNG с контурами, границами
   и номерами ячеек пишется в _diagnostics/ рядом с кадрами.

Имена кадров _NNN_DDD.png: NNN — исходный номер ячейки шита (row-major);
пропуск ячейки не сжимает нумерацию (виден в имени и в манифесте).
loop в плане — индексы ИСХОДНЫХ ячеек; в манифест записываются позиции
записанных кадров (map_loop), индексация рантайма не меняется.

Нормализация размера: эталон REF_HEIGHT_PX = 458 (высота Idle/Normal),
авто-scale = 458 / медианная высота кадра (эффекты не меняют масштаб всей
анимации); стоп-лист AUTO_SCALE_STOP и ручной scale плана перезаписывают.
Клип с mirror_from не режется — зеркально отражается уже нарезанный клип.

Запуск (с любой директории):
    .venv/bin/python scripts/slice_sheets.py [ИСХОДНЫЙ_КАТАЛОГ]
"""

from __future__ import annotations

import os
import statistics
import sys
from collections import deque
from dataclasses import dataclass, field
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QGuiApplication, QImage, QPainter, QTransform

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SRC = Path("/home/fake-cat/projects/animation")
OUT_ROOT = ROOT / "assets" / "characters" / "malinka"

# Структурный порог alpha: эффекты и полупрозрачный контент участвуют в
# определении границ; более светлая кайма привязывается к компонентам (BFS)
ALPHA_STRUCT = 16
# Компоненты меньше порога — мусор (сколы 1..9 px); искры ANGRY (33+ px) — крупные
MIN_COMPONENT_PX = 10
# Спрайт кадра: площадь >= доли максимума шита (мелкие эффекты и сколы —
# сателлиты, привязываются кадру ближайшего спрайта)
SPRITE_MIN_SHARE = 0.35
# Доля пикселей компонента в чужом слоте: >= — «слитый» компонент (пиксельно
# соединённые кадры), меньше — кроссовер одного кадра, компонент целый
SPLIT_MIN_SHARE = 0.25
# Отклонение контента кадра от слота > доли слота — предупреждение (чужой фрагмент)
SLOT_DEVIATION_SHARE = 0.5
# Высота кадра вне [1/HEIGHT_ANOMALY, HEIGHT_ANOMALY] от медианы — аномалия
HEIGHT_ANOMALY = 3.0
# Нормализация: эталон — высота Idle/Normal; авто-scale = REF / медиана высот кадров
REF_HEIGHT_PX = 458
# Стоп-лист авто-нормализации: сидячая/приседающая поза росла бы неестественно
AUTO_SCALE_STOP = frozenset({"Sit/Typing", "Hide/Out"})

MODE_AUTO = "auto"  # реальные промежутки между кадрами
MODE_GRID = "grid"  # фиксированная сетка rows×cols (строго регулярные шиты)
MODE_MANUAL = "manual"  # явные границы колонок (контролируемый fallback)


@dataclass(frozen=True, slots=True)
class ClipPlan:
    """План нарезки одного шита: имя клипа, длительность, спека."""

    sheet: str  # каталог-источник (имя шита в animation/)
    anim: str  # каталог «Анимация» (префикс состояний FSM)
    state: str  # каталог «Состояние»
    duration_ms: int  # длительность кадра в имени _NNN_DDD.png
    # --- playback-спека (индексы ИСХОДНЫХ ячеек шита, включительно) ---
    loop: tuple[int, int] | None = None  # повторяемый сегмент; None → весь/однократно
    once: bool = False  # сыграть один раз и завершиться
    prefix_once: bool = False  # кадры до loop — один раз перед циклом
    suffix_on_exit: bool = False  # после loop доиграть хвост при выходе
    repeat_fill_ms: int | None = None  # «несколько раз»: заполнить цель случ. числом повторов
    mirror: str | None = None  # "left" — loop-сегмент зеркалится (спрайт смотрит влево)
    motion: str = "none"  # walk / traverse / none
    scale: float = 1.0  # рантайм-масштаб (авто может перезаписать)
    mirror_from: str | None = None  # вместо шита — зеркально отразить клип Anim/State
    notes: str = ""
    # --- режим нарезки и валидация ---
    mode: str = MODE_AUTO  # auto / grid / manual
    grid: tuple[int, int] | None = None  # (rows, cols) — для mode="grid"
    col_bounds: tuple[tuple[int, ...], ...] | tuple[int, ...] | None = None
    # границы колонок (len = cols+1); плоский кортеж — на все ряды,
    # кортеж кортежей — на каждый ряд; для mode="manual"
    expect: int | None = None  # ожидаемое число ячеек шита (валидация детекта)


# Шит → клип. Длительности — по характеру движения (старый план slice_malinka).
PLANS: tuple[ClipPlan, ...] = (
    ClipPlan("ANGRY", "Angry", "Normal", 100, loop=(4, 10), repeat_fill_ms=4000, expect=12),
    ClipPlan("COFFEE", "Coffee", "Normal", 200, loop=(1, 9), expect=12),
    ClipPlan("DANCING", "Dance", "Normal", 120, loop=(2, 10), expect=12),
    ClipPlan("ERROR_PANIC", "Error", "Panic", 100, once=True, expect=12),
    ClipPlan("HAPPY_SUCCESS", "Happy", "Success", 120, once=True, expect=12),
    # Движение окна только у ходьбы (решение пользователя): остальные клипы статичны
    ClipPlan("HIDE OUT", "Hide", "Out", 150, once=True, expect=12),
    ClipPlan("IDLE", "Idle", "Normal", 150, once=True, expect=12),
    ClipPlan("LIE DORMANT", "Lie", "Dormant", 300, once=True, expect=10),
    # Переходный клип: каждая смена анимации начинается с него (player.set_transition).
    # Шит без пустых промежутков между спрайтами и со «слитым» компонентом —
    # ручные границы: долины x969 (слитая пара) и x284 (перекрытие bbox).
    ClipPlan(
        "MOVED CLIP",
        "Move",
        "Transition",
        100,
        once=True,
        expect=12,
        mode=MODE_MANUAL,
        col_bounds=(
            (0, 222, 455, 713, 969, 1207, 1448),
            (0, 284, 535, 781, 1005, 1239, 1448),
        ),
    ),
    ClipPlan("SITTING HAPPILLY", "Sit", "Happily", 250, loop=(3, 11), expect=12),
    ClipPlan("SIT_SLEEP_WAKE", "Sleep", "Wake", 250, loop=(4, 9), suffix_on_exit=True, expect=12),
    ClipPlan("TALKING", "Talk", "Normal", 150, loop=(0, 11), expect=12),
    ClipPlan("THINKING", "Thinking", "Normal", 200, once=True, expect=12),
    # loop 6–9: кадры 0–5/10–11 дефектные (ручная правка clips.toml закреплена в плане)
    ClipPlan("TYPING", "Sit", "Typing", 250, loop=(6, 9), expect=12),
    # ячейка 6 шита пуста — цикл ходьбы 7..11 (5 записанных кадров)
    ClipPlan("WALK BACK", "Walk", "Back", 120, loop=(7, 11), motion="walk", expect=12),
    ClipPlan(
        "WALK DIRECT", "Walk", "Direct", 120, loop=(2, 10), mirror="left", motion="walk", expect=12
    ),
    ClipPlan(
        "WALK RIGHT",
        "Walk",
        "Right",
        120,
        loop=(2, 10),
        motion="walk",
        expect=12,
        notes="спрайт мельче остальных (h≈333) — нормализуется авто-scale",
    ),
    # Ходьба влево: зеркало Walk/Right (шита-источника нет, план с mirror_from)
    ClipPlan(
        "(mirror WALK RIGHT)",
        "Walk",
        "Left",
        120,
        loop=(2, 10),
        motion="walk",
        mirror_from="Walk/Right",
    ),
    ClipPlan("WELCOME", "Welcome", "Greeting", 150, once=True, expect=12),
)


@dataclass(slots=True)
class Component:
    """Связной компонент alpha-маски (8-связность) с его пикселями."""

    pixels: list[int]  # y * w + x структуры (без каймы)
    x0: int
    y0: int
    x1: int
    y1: int
    row: int = -1  # ряд шита (полоса Y)
    frame: int = -1  # позиция кадра-владельца; -1 — не назначен
    split: bool = False  # «слитый» компонент разрезан по границе (GRID/MANUAL)
    fringe: list[int] = field(default_factory=list)  # кайма (полупрозрачные края)

    @property
    def area(self) -> int:
        return len(self.pixels)

    @property
    def all_pixels(self) -> list[int]:
        return self.pixels + self.fringe

    @property
    def major(self) -> bool:
        return len(self.pixels) >= MIN_COMPONENT_PX

    def grow(self, x: int, y: int) -> None:
        self.x0 = min(self.x0, x)
        self.x1 = max(self.x1, x)
        self.y0 = min(self.y0, y)
        self.y1 = max(self.y1, y)


@dataclass(slots=True)
class Segment:
    """Кадр шита: ячейка (row, col) с привязкой к слоту сетки."""

    row: int
    col: int
    source_index: int  # исходный номер ячейки шита (row-major)
    slot_x0: int  # слот — стабильная привязка кадра (не bbox)
    slot_x1: int  # включительно
    pixels: list[int] = field(default_factory=list)  # пиксели кадра (компоненты + кайма)
    x0: int = -1  # фактический контент (валидация/диагностика)
    x1: int = -1
    y0: int = -1
    y1: int = -1

    def add(self, index: int, width: int) -> None:
        self.pixels.append(index)
        x, y = index % width, index // width
        if self.x0 < 0:
            self.x0 = self.x1 = x
            self.y0 = self.y1 = y
        else:
            self.x0 = min(self.x0, x)
            self.x1 = max(self.x1, x)
            self.y0 = min(self.y0, y)
            self.y1 = max(self.y1, y)


@dataclass(slots=True)
class SliceResult:
    """Итог нарезки одного шита."""

    plan: ClipPlan
    sheet_w: int = 0
    sheet_h: int = 0
    mode: str = MODE_AUTO
    rows: int = 0  # рядов шита (полос Y)
    cols: int = 0  # колонок (после выравнивания рядов)
    frames_written: int = 0
    sheet_cells: list[int] = field(default_factory=list)  # позиция → исходная ячейка
    missing_cells: list[int] = field(default_factory=list)  # пустые ячейки (пропущены)
    content_h: int = 0  # медианная высота кадра (авто-scale, без учёта эффектов)
    scale: float = 1.0
    loop_positions: tuple[int, int] | None = None  # loop плана → позиции записанных кадров
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


def content_mask(image: QImage) -> tuple[bytearray, int, int]:
    """Бинарная маска структурного контента (alpha >= ALPHA_STRUCT)."""
    image = image.convertToFormat(QImage.Format.Format_RGBA8888)
    data = bytes(image.constBits())
    stride = image.bytesPerLine()
    width, height = image.width(), image.height()
    mask = bytearray(width * height)
    for y in range(height):
        row = y * stride
        base = y * width
        for x in range(width):
            if data[row + x * 4 + 3] >= ALPHA_STRUCT:
                mask[base + x] = 1
    return mask, width, height


def contiguous_bands(flags: list[bool]) -> list[tuple[int, int]]:
    """Максимальные участки подряд идущих True → [(start, end включительно)]."""
    out: list[tuple[int, int]] = []
    start: int | None = None
    for i, flag in enumerate(flags):
        if flag and start is None:
            start = i
        elif not flag and start is not None:
            out.append((start, i - 1))
            start = None
    if start is not None:
        out.append((start, len(flags) - 1))
    return out


def label_components(mask: bytearray, width: int, height: int) -> list[Component]:
    """Связные компоненты маски (8-связность) с пикселями; порядок — как найдены."""
    comps: list[Component] = []
    seen = bytearray(width * height)
    for start in range(width * height):
        if not mask[start] or seen[start]:
            continue
        queue = deque([start])
        seen[start] = 1
        pixels: list[int] = []
        x0 = y0 = width + height
        x1 = y1 = -1
        while queue:
            p = queue.popleft()
            pixels.append(p)
            px, py = p % width, p // width
            x0 = min(x0, px)
            x1 = max(x1, px)
            y0 = min(y0, py)
            y1 = max(y1, py)
            for dy in (-1, 0, 1):
                ny = py + dy
                if ny < 0 or ny >= height:
                    continue
                for dx in (-1, 0, 1):
                    nx = px + dx
                    if nx < 0 or nx >= width:
                        continue
                    q = ny * width + nx
                    if mask[q] and not seen[q]:
                        seen[q] = 1
                        queue.append(q)
        comps.append(Component(pixels=pixels, x0=x0, y0=y0, x1=x1, y1=y1))
    return comps


def attach_fringe(
    image: QImage, width: int, height: int, comps: list[Component], depth: int = 2
) -> None:
    """Полупрозрачная кайма (0 < alpha < ALPHA_STRUCT) — к ближайшему компоненту.

    Антиалиасинг и мягкие края сохраняются 1:1 и принадлежат тому же кадру,
    что и соседний структурный пиксель (волна BFS от компонентов, не глубже
    depth px — глубокая дымка шита не «раздувает» компоненты и не склеивает
    промежутки между кадрами).
    """
    labels = [0] * (width * height)
    for cid, comp in enumerate(comps, start=1):
        for p in comp.pixels:
            labels[p] = cid
    data = bytes(image.constBits())
    stride = image.bytesPerLine()
    fringe: dict[int, list[int]] = {}
    frontier = [p for p, lab in enumerate(labels) if lab]
    for _ in range(depth):
        new_frontier: list[int] = []
        for p in frontier:
            lab = labels[p]
            px, py = p % width, p // width
            for dy in (-1, 0, 1):
                ny = py + dy
                if ny < 0 or ny >= height:
                    continue
                for dx in (-1, 0, 1):
                    nx = px + dx
                    if nx < 0 or nx >= width:
                        continue
                    q = ny * width + nx
                    if labels[q]:
                        continue
                    if data[ny * stride + nx * 4 + 3] > 0:
                        labels[q] = lab
                        new_frontier.append(q)
                        fringe.setdefault(lab, []).append(q)
        frontier = new_frontier
        if not frontier:
            break
    for lab, pixels in fringe.items():
        comp = comps[lab - 1]
        for p in pixels:
            comp.grow(p % width, p // width)
        comp.fringe.extend(pixels)


def major_flags(comps: list[Component], width: int, height: int) -> bytearray:
    """Маска только крупных компонентов: мусор не участвует в поиске промежутков."""
    out = bytearray(width * height)
    for comp in comps:
        if comp.major:
            for p in comp.pixels:
                out[p] = 1
    return out


def row_bands(flags: bytearray, width: int, height: int) -> list[tuple[int, int]]:
    """Ряды шита: полосы контента по Y (пустые промежутки — разделители)."""
    return contiguous_bands(
        [any(flags[y * width : (y + 1) * width]) for y in range(height)]
    )


def sprite_components(comps: list[Component]) -> list[Component]:
    """Спрайты шита: компоненты с площадью >= SPRITE_MIN_SHARE от максимума.

    Кадр анимации — спрайт-компонент; пиксельно несоединённые детали
    (искры, мусор) — его сателлиты, а не самостоятельные кадры.
    """
    majors = [comp for comp in comps if comp.major]
    if not majors:
        return []
    peak = max(comp.area for comp in majors)
    sprites = [comp for comp in majors if comp.area >= SPRITE_MIN_SHARE * peak]
    return sprites or majors


def align_sprite_columns(row_sprites: list[list[Component]]) -> tuple[int, list[list[int]]]:
    """Колонки спрайтов: порядок + ближайший центр к эталонному ряду.

    Эталон — ряд с максимумом спрайтов: пустая ячейка другого ряда не
    занижает нумерацию (колонка видна из эталона). Bbox спрайтов могут
    перекрываться (кроссоверы) — колонка определяется по центру спрайта.
    """
    ref_index = max(range(len(row_sprites)), key=lambda r: len(row_sprites[r]))
    ref = row_sprites[ref_index]
    cols = len(ref)
    out: list[list[int]] = []
    for row in row_sprites:
        used: set[int] = set()
        row_cols: list[int] = []
        for comp in row:
            center = (comp.x0 + comp.x1) / 2
            candidates = sorted(
                range(cols), key=lambda c: (abs((ref[c].x0 + ref[c].x1) / 2 - center), c)
            )
            col = next((c for c in candidates if c not in used), candidates[0])
            used.add(col)
            row_cols.append(col)
        out.append(row_cols)
    return cols, out


def auto_slots(
    row_cols: list[list[tuple[int, int]]],
    aligns: list[list[int]],
    cols: int,
) -> list[list[tuple[int, int]]]:
    """Слоты сетки AUTO: равномерный шаг по полосам ряда (устойчиво к bbox).

    Шаг и начало — медиана по парам соседних полос: слот не зависит от
    контента конкретного кадра, кадры кладутся на холст без дёрганья.
    """
    out: list[list[tuple[int, int]]] = []
    pitches: list[float] = []
    for bands, align in zip(row_cols, aligns, strict=True):
        for (x0a, _), (x0b, _), ca, cb in zip(bands, bands[1:], align, align[1:], strict=False):
            if cb > ca:
                pitches.append((x0b - x0a) / (cb - ca))
    fallback = statistics.median(pitches) if pitches else 0.0
    for bands, align in zip(row_cols, aligns, strict=True):
        if not bands:  # ряд без спрайтов — слоты по общему шагу
            step = fallback or 1
            out.append(
                [(round(c * step), round((c + 1) * step) - 1) for c in range(cols)]
            )
            continue
        row_pitches = [
            (x0b - x0a) / (cb - ca)
            for (x0a, _), (x0b, _), ca, cb in zip(bands, bands[1:], align, align[1:], strict=False)
            if cb > ca
        ]
        single = [(x1 - x0 + 1) + 1 for x0, x1 in bands]
        pitch = statistics.median(row_pitches) if row_pitches else (fallback or single[0])
        starts = [x0 - col * pitch for (x0, _), col in zip(bands, align, strict=True)]
        start = statistics.median(starts)
        out.append(
            [
                (round(start + col * pitch), round(start + (col + 1) * pitch) - 1)
                for col in range(cols)
            ]
        )
    return out


def uniform_slots(width: int, cols: int) -> list[tuple[int, int]]:
    """Слоты GRID: равномерное деление ширины шита."""
    step = width / cols
    bounds = [round(i * step) for i in range(cols + 1)]
    bounds[0], bounds[-1] = 0, width
    return [(bounds[c], bounds[c + 1] - 1) for c in range(cols)]


def valley_candidates(
    flags: bytearray, width: int, y0: int, y1: int, band: tuple[int, int]
) -> list[int]:
    """Кандидаты-разделители слитого участка: X с минимумом контента (долины)."""
    bx0, bx1 = band
    counts = [sum(flags[y * width + x] for y in range(y0, y1 + 1)) for x in range(bx0, bx1 + 1)]
    if not counts:
        return []
    peak = max(counts)
    out = [
        bx0 + i
        for i, count in enumerate(counts)
        if 0 < i < len(counts) - 1 and count <= peak * 0.12
    ]
    # сжать соседние кандидаты в один (центр группы)
    groups: list[list[int]] = []
    for x in out:
        if groups and x - groups[-1][-1] <= 3:
            groups[-1].append(x)
        else:
            groups.append([x])
    return [sum(group) // len(group) for group in groups]


def col_of(slots: list[tuple[int, int]], x: int) -> int:
    """Колонка (слот), содержащая x; за краями — ближайшая."""
    for col, (_x0, x1) in enumerate(slots):
        if x <= x1:
            return col
    return len(slots) - 1


def set_comp_rows(comps: list[Component], y_bands: list[tuple[int, int]]) -> None:
    """Ряд каждого компонента: полоса Y по вертикали (мусор — к ближайшей)."""
    for comp in comps:
        comp.row = min(
            range(len(y_bands)),
            key=lambda r: max(y_bands[r][0] - comp.y1, comp.y0 - y_bands[r][1], 0),
        )


def _place(
    comp: Component,
    segments: dict[tuple[int, int], Segment],
    row: int,
    col: int,
    pixels: list[int],
    width: int,
) -> None:
    """Поместить пиксели компонента (целиком или часть) в кадр (row, col)."""
    seg = segments.get((row, col))
    if seg is None:
        return
    for p in pixels:
        seg.add(p, width)
    comp.frame = seg.source_index


def assign_auto(
    comps: list[Component],
    segments: dict[tuple[int, int], Segment],
    sprite_frame: list[tuple[Component, int, int]],
    width: int,
) -> None:
    """AUTO: кадр — спрайт-компонент целиком; сателлиты — кадру ближайшего спрайта.

    Спрайты пиксельно несоединены → принадлежность однозначна; кроссоверы
    (перекрытие bbox соседних кадров) не режутся — компонент пишется целиком.
    """
    sprite_ids = {id(comp) for comp, _, _ in sprite_frame}
    for comp, row, col in sprite_frame:
        _place(comp, segments, row, col, comp.all_pixels, width)
    for comp in comps:
        if id(comp) in sprite_ids:
            continue
        nearest = min(
            sprite_frame,
            key=lambda item: max(item[0].x0 - comp.x1, comp.x0 - item[0].x1, 0)
            + max(item[0].y0 - comp.y1, comp.y0 - item[0].y1, 0),
        )
        _place(comp, segments, nearest[1], nearest[2], comp.all_pixels, width)


def assign_slots(
    comps: list[Component],
    segments: dict[tuple[int, int], Segment],
    slots: dict[int, list[tuple[int, int]]],
    width: int,
    result: SliceResult,
) -> None:
    """GRID/MANUAL: компонент целиком — кадру большинства пикселей.

    Кроссовер одного кадра не режется (компонент целиком, хвост выходит за
    слот). «Слитый» компонент (масса ≥ SPLIT_MIN_SHARE в двух слотах —
    пиксельно соединённые кадры) режется по границам слотов: контролируемый
    разрез с предупреждением; мелкие части разреза сливаются с соседней.
    """
    major_col: dict[int, int] = {}
    for comp in (c for c in comps if c.major):
        row_slots = slots[comp.row]
        pixels = comp.all_pixels
        buckets: dict[int, list[int]] = {}
        for p in pixels:
            buckets.setdefault(col_of(row_slots, p % width), []).append(p)
        total = len(pixels)
        top_col = max(buckets, key=lambda col: len(buckets[col]))
        major_col[id(comp)] = top_col
        if total - len(buckets[top_col]) < SPLIT_MIN_SHARE * total:
            _place(comp, segments, comp.row, top_col, pixels, width)
            continue
        # «слитый» компонент: части по слотам, мелкие — к соседней части
        comp.split = True
        parts: list[list[list[int]]] = [
            [col, list(pixels)] for col, pixels in sorted(buckets.items())
        ]
        changed = True
        while changed and len(parts) > 1:
            changed = False
            for i, part in enumerate(parts):
                if len(part[1]) >= SPLIT_MIN_SHARE * total:
                    continue
                prev = parts[i - 1] if i > 0 else None
                nxt = parts[i + 1] if i + 1 < len(parts) else None
                if prev is not None and (nxt is None or len(prev[1]) >= len(nxt[1])):
                    target = prev
                else:
                    target = nxt
                if target is not None:
                    target[1].extend(part[1])
                    del parts[i]
                    changed = True
                    break
        for part in parts:
            part_counts: dict[int, int] = {}
            if len(part[1]) > len(buckets[major_col[id(comp)]]):
                major_col[id(comp)] = col_of(row_slots, part[1][0])
            for p in part[1]:
                part_col = col_of(row_slots, p % width)
                part_counts[part_col] = part_counts.get(part_col, 0) + 1
            part_col = max(part_counts, key=lambda col: part_counts[col])
            _place(comp, segments, comp.row, part_col, part[1], width)
        result.warnings.append(
            f"компонент разрезан по границе слотов на {len(parts)} частей: "
            f"{comp.area} px, bbox x{comp.x0}..{comp.x1} y{comp.y0}..{comp.y1}"
        )
    for comp in (c for c in comps if not c.major):
        majors = [c for c in comps if c.major and c.row == comp.row and id(c) in major_col]
        if majors:
            nearest = min(
                majors,
                key=lambda c: max(c.x0 - comp.x1, comp.x0 - c.x1, 0)
                + max(c.y0 - comp.y1, comp.y0 - c.y1, 0),
            )
            nearest_col = major_col[id(nearest)]
            _place(comp, segments, comp.row, nearest_col, comp.all_pixels, width)
        else:
            fallback_col = col_of(slots[comp.row], comp.x0)
            _place(comp, segments, comp.row, fallback_col, comp.all_pixels, width)


def map_loop(
    loop: tuple[int, int], source_indices: list[int], result: SliceResult
) -> tuple[int, int] | None:
    """Индексы плана (исходные ячейки) → позиции записанных кадров (манифест).

    Пропуск ячейки внутри диапазона ломает семантику loop — ошибка, а не
    молчаливый сдвиг индексов.
    """
    lo, hi = loop
    positions = [pos for pos, src in enumerate(source_indices) if lo <= src <= hi]
    if not positions:
        result.errors.append(f"loop {list(loop)} не пересекается с записанными кадрами")
        return None
    missing = [src for src in range(lo, hi + 1) if src not in source_indices]
    if missing:
        result.warnings.append(
            f"loop {list(loop)}: исходные ячейки {missing} пусты — в цикл войдут только записанные"
        )
    return positions[0], positions[-1]


def check_merged_components(
    comps: list[Component],
    sprite_frame: list[tuple[Component, int, int]],
    y_bands: list[tuple[int, int]],
    flags: bytearray,
    width: int,
    result: SliceResult,
) -> None:
    """Спрайт-компонент, похожий на несколько слитых кадров, — ошибка.

    Пиксельно соединённые персонажи не распределяются автоматически: скрипт
    сообщает кандидатов-разделителей и требует mode="manual" с col_bounds.
    """
    sprites = [comp for comp, _, _ in sprite_frame]
    if not sprites:
        return
    med_w = statistics.median(comp.x1 - comp.x0 + 1 for comp in sprites)
    med_a = statistics.median(comp.area for comp in sprites)
    for comp in sprites:
        wide = comp.x1 - comp.x0 + 1 > 1.75 * med_w
        heavy = comp.area > 1.75 * med_a
        if not (wide and heavy):
            continue
        cand = valley_candidates(
            flags, width, y_bands[comp.row][0], y_bands[comp.row][1], (comp.x0, comp.x1)
        )
        result.errors.append(
            f"компонент {comp.area} px (ширина {comp.x1 - comp.x0 + 1}, медиана {med_w:.0f}) "
            f"похож на несколько слитых кадров — принадлежность не определяется; "
            f'укажите mode="manual" с col_bounds; кандидаты разделителей: {cand}'
        )


def resolve_sheet_dir(src_root: Path, sheet: str) -> Path | None:
    """Каталог шита: точное имя, иначе совпадение по нормализованным пробелам.

    Имена каталогов источника содержат случайные пробелы («SITTING  HAPPILY») —
    план хранит нормализованное имя; схлопывание пробелов + casefold, точное
    совпадение проверяется первым.
    """

    def norm(name: str) -> str:
        return " ".join(name.split()).casefold()

    exact = src_root / sheet
    if exact.is_dir():
        return exact
    for entry in sorted(src_root.iterdir()):
        if entry.is_dir() and norm(entry.name) == norm(sheet):
            return entry
    return None


def slice_sheet(plan: ClipPlan, src_root: Path) -> SliceResult:
    """Нарезать один шит: масочная нарезка кадров + валидация + диагностика."""
    result = SliceResult(plan=plan, mode=plan.mode)
    sheet_dir = resolve_sheet_dir(src_root, plan.sheet)
    if sheet_dir is None:
        result.errors.append(f"нет каталога шита {plan.sheet} в {src_root}")
        return result
    sheet_path = sheet_dir / "sheet.png"
    img = QImage(str(sheet_path))
    if img.isNull():
        result.errors.append(f"не удалось открыть {sheet_path}")
        return result
    img = img.convertToFormat(QImage.Format.Format_RGBA8888)
    result.sheet_w, result.sheet_h = img.width(), img.height()
    width, height = result.sheet_w, result.sheet_h

    # --- анализ: компоненты, кайма, ряды ---
    mask, _, _ = content_mask(img)
    comps = label_components(mask, width, height)
    attach_fringe(img, width, height, comps)
    flags = major_flags(comps, width, height)
    y_bands = row_bands(flags, width, height)
    if not y_bands:
        result.errors.append(f"в шите {plan.sheet} нет контента")
        return result
    result.rows = len(y_bands)
    set_comp_rows(comps, y_bands)

    # --- сегментация колонок по режиму ---
    segments: dict[tuple[int, int], Segment] = {}
    slots: dict[int, list[tuple[int, int]]] = {}
    sprite_frame: list[tuple[Component, int, int]] = []
    if plan.mode == MODE_AUTO:
        sprites = sprite_components(comps)
        row_sprites: list[list[Component]] = [
            sorted((c for c in sprites if c.row == row), key=lambda c: c.x0)
            for row in range(result.rows)
        ]
        if not any(row_sprites):
            result.errors.append(f"в шите {plan.sheet} нет спрайтов (крупных компонентов)")
            return result
        result.cols, col_lists = align_sprite_columns(row_sprites)
        row_ranges = [[(c.x0, c.x1) for c in row] for row in row_sprites]
        slots_list = auto_slots(row_ranges, col_lists, result.cols)
        for row in range(result.rows):
            slots[row] = slots_list[row]
            for comp, col in zip(row_sprites[row], col_lists[row], strict=True):
                sprite_frame.append((comp, row, col))
    elif plan.mode == MODE_GRID:
        if plan.grid is None:
            result.errors.append('mode="grid" требует grid=(rows, cols)')
            return result
        grow, result.cols = plan.grid
        if grow != result.rows:
            result.errors.append(f"grid rows={grow}, а рядов шита {result.rows}")
            return result
        for row in range(result.rows):
            slots[row] = uniform_slots(width, result.cols)
    else:
        bounds = plan.col_bounds
        if bounds is None:
            result.errors.append('mode="manual" требует col_bounds')
            return result
        if isinstance(bounds[0], int):
            per_row = [tuple(bounds)] * result.rows
        else:
            per_row = [tuple(b) for b in bounds]
        if len(per_row) != result.rows:
            result.errors.append(
                f"col_bounds описывает {len(per_row)} рядов, а рядов шита {result.rows}"
            )
            return result
        counts = {len(b) - 1 for b in per_row}
        if len(counts) != 1:
            result.errors.append(
                "границы колонок рядов различаются — число колонок должно совпадать"
            )
            return result
        result.cols = counts.pop()
        for row, b in enumerate(per_row):
            slots[row] = [(b[col], b[col + 1] - 1) for col in range(result.cols)]
    for row in range(result.rows):
        for col in range(result.cols):
            x0, x1 = slots[row][col]
            segments[(row, col)] = Segment(
                row=row,
                col=col,
                source_index=row * result.cols + col,
                slot_x0=x0,
                slot_x1=x1,
            )

    # --- валидация детекта до всякой записи ---
    cells = result.rows * result.cols
    if plan.expect is not None and cells != plan.expect:
        result.errors.append(
            f"детект {result.rows}x{result.cols} = {cells} ячеек, ожидалось {plan.expect}"
        )
    if plan.mode == MODE_AUTO:
        check_merged_components(comps, sprite_frame, y_bands, flags, width, result)
    if result.errors:
        # ошибки диагностики видны до экспорта: контуры и границы в _diagnostics/
        write_diagnostics(img, plan, comps, segments, result)
        return result

    # --- принадлежность компонентов кадрам ---
    if plan.mode == MODE_AUTO:
        assign_auto(comps, segments, sprite_frame, width)
    else:
        assign_slots(comps, segments, slots, width, result)
    sliced = write_frames(img, plan, segments, y_bands, result)
    write_diagnostics(img, plan, comps, segments, sliced)
    return sliced


def write_frames(
    img: QImage,
    plan: ClipPlan,
    segments: dict[tuple[int, int], Segment],
    y_bands: list[tuple[int, int]],
    result: SliceResult,
) -> SliceResult:
    """Вырезать кадры по маске компонентов и сохранить PNG + манифест-данные.

    В кадр попадают ТОЛЬКО пиксели его компонентов (включая кайму): чужие
    пиксели внутри bbox не копируются. Кадр кладётся на холст относительно
    слота сетки — привязка не зависит от bbox, дёрганья нет.
    """
    width, height = result.sheet_w, result.sheet_h
    all_segs = sorted(segments.values(), key=lambda seg: seg.source_index)
    for seg in all_segs:
        if not seg.pixels:
            result.missing_cells.append(seg.source_index)
            result.warnings.append(
                f"ячейка {seg.source_index} без пикселей — кадр пропущен "
                f"(row={seg.row} col={seg.col})"
            )
    written = [seg for seg in all_segs if seg.pixels]
    if not written:
        result.errors.append(f"в шите {plan.sheet} нет ни одного кадра с контентом")
        return result

    source_indices = [seg.source_index for seg in written]
    result.sheet_cells = source_indices
    if plan.loop is not None:
        loop_pos = map_loop(plan.loop, source_indices, result)
        if loop_pos is None:
            return result
        result.loop_positions = loop_pos

    # --- геометрия холста: слот + кроссоверы, пол канвы — низ ряда ---
    left = max(max(seg.slot_x0 - seg.x0 for seg in written), 0)
    clip_w = left + max(seg.x1 - seg.slot_x0 + 1 for seg in written)
    row_y0: dict[int, int] = {}
    row_y1: dict[int, int] = {}
    for seg in written:
        row_y0[seg.row] = min(row_y0.get(seg.row, seg.y0), seg.y0)
        row_y1[seg.row] = max(row_y1.get(seg.row, seg.y1), seg.y1)
    row_h = {row: row_y1[row] - row_y0[row] + 1 for row in row_y0}
    clip_h = max(row_h.values())

    line_dir = OUT_ROOT / plan.anim / plan.state / "1"
    line_dir.mkdir(parents=True, exist_ok=True)
    for old in line_dir.glob("_*.png"):  # идемпотентный перезапуск
        old.unlink()

    src = memoryview(img.constBits())
    stride = img.bytesPerLine()
    for seg in written:
        canvas = QImage(clip_w, clip_h, QImage.Format.Format_RGBA8888)
        canvas.fill(QColor(0, 0, 0, 0))
        dst = canvas.bits()
        dst_stride = canvas.bytesPerLine()
        for p in seg.pixels:
            x, y = p % width, p // width
            dx = x - seg.slot_x0 + left
            dy = clip_h - row_h[seg.row] + (y - row_y0[seg.row])
            di = dy * dst_stride + dx * 4
            si = y * stride + x * 4
            dst[di : di + 4] = src[si : si + 4]
        # имя несёт ИСХОДНЫЙ номер ячейки — пропуски не сжимают нумерацию
        path = line_dir / f"_{seg.source_index:03d}_{plan.duration_ms}.png"
        if not canvas.save(str(path)):
            result.errors.append(f"не сохранился: {path}")
            continue
        result.frames_written += 1

    # --- валидации кадров ---
    heights = [seg.y1 - seg.y0 + 1 for seg in written]
    med_h = statistics.median(heights)
    for seg in written:
        tag = f"ячейка {seg.source_index}"
        slot_w = seg.slot_x1 - seg.slot_x0 + 1
        deviation = max(seg.slot_x0 - seg.x0, seg.x1 - seg.slot_x1, 0)
        if deviation > SLOT_DEVIATION_SHARE * slot_w:
            result.warnings.append(
                f"{tag}: контент отклоняется от слота на {deviation} px "
                f"(слот {slot_w} px) — возможен чужой фрагмент"
            )
        h = seg.y1 - seg.y0 + 1
        if med_h and (h > med_h * HEIGHT_ANOMALY or h * HEIGHT_ANOMALY < med_h):
            result.warnings.append(
                f"{tag}: высота {h} px аномальна (медиана {med_h:.0f})"
            )
        if seg.x0 == 0 or seg.y0 == 0 or seg.x1 == width - 1 or seg.y1 == height - 1:
            result.warnings.append(f"{tag}: контент касается края шита (возможен обрез)")

    result.content_h = int(round(med_h))
    result.scale = auto_scale_for(f"{plan.anim}/{plan.state}", result.content_h)
    return result


def auto_scale_for(clip_name: str, content_h: int) -> float:
    """Авто-масштаб клипа: эталон / медианная высота кадра; стоп-лист — 1.0.

    Медиана, а не максимум: эффекты и прыжки не меняют масштаб всей анимации.
    """
    if clip_name in AUTO_SCALE_STOP or content_h <= 0:
        return 1.0
    return REF_HEIGHT_PX / content_h


def mirror_clip(plan: ClipPlan) -> SliceResult:
    """Зеркально отразить по X уже нарезанный клип (plan.mirror_from) → новый клип.

    Используется для ходьбы влево: Walk/Left = отражение Walk/Right — отдельного
    шита-источника нет. Имена кадров (исходные номера ячеек) сохраняются.
    """
    if plan.mirror_from is None:  # защита: вызывается только для mirror-планов
        raise ValueError(f"у плана {plan.sheet} нет mirror_from")
    src_dir = OUT_ROOT / plan.mirror_from / "1"
    dst_dir = OUT_ROOT / plan.anim / plan.state / "1"
    result = SliceResult(plan=plan)
    frames = sorted(src_dir.glob("_*_*.png"))
    if not frames:
        result.errors.append(f"нет кадров-источника {src_dir} для зеркальной нарезки")
        return result
    dst_dir.mkdir(parents=True, exist_ok=True)
    for old in dst_dir.glob("_*.png"):  # идемпотентный перезапуск без stale-кадров
        old.unlink()
    for src_path in frames:
        image = QImage(str(src_path))
        if image.isNull():
            result.errors.append(f"не удалось прочитать кадр {src_path}")
            continue
        result.sheet_w, result.sheet_h = image.width(), image.height()
        # FastTransformation — точное пиксельное отражение без сглаживания
        mirrored = image.transformed(
            QTransform().scale(-1, 1), Qt.TransformationMode.FastTransformation
        )
        if not mirrored.save(str(dst_dir / src_path.name), "PNG"):
            result.errors.append(f"не удалось сохранить {dst_dir / src_path.name}")
            continue
        result.frames_written += 1
    return result


# Растровые цифры 3x5: drawText падает в offscreen под QApplication
# (шрифтовой движок Qt), диагностика обязана работать и в тестах
DIGITS: dict[str, tuple[str, ...]] = {
    "0": ("###", "#.#", "#.#", "#.#", "###"),
    "1": (".#.", "##.", ".#.", ".#.", "###"),
    "2": ("###", "..#", "###", "#..", "###"),
    "3": ("###", "..#", "###", "..#", "###"),
    "4": ("#.#", "#.#", "###", "..#", "..#"),
    "5": ("###", "#..", "###", "..#", "###"),
    "6": ("###", "#..", "###", "#.#", "###"),
    "7": ("###", "..#", "..#", "..#", "..#"),
    "8": ("###", "#.#", "###", "#.#", "###"),
    "9": ("###", "#.#", "###", "..#", "###"),
}


def draw_number(painter: QPainter, x: int, y: int, value: int, color: QColor) -> None:
    """Нарисовать число растровыми цифрами (масштаб 2 px на пиксель глифа)."""
    painter.setPen(color)
    painter.setBrush(color)
    cursor = x
    for char in str(value):
        glyph = DIGITS[char]
        for row, line in enumerate(glyph):
            for col, cell in enumerate(line):
                if cell == "#":
                    painter.drawRect(cursor + col * 2, y + row * 2, 2, 2)
        cursor += 8
    painter.setBrush(Qt.BrushStyle.NoBrush)


def write_diagnostics(
    img: QImage,
    plan: ClipPlan,
    comps: list[Component],
    segments: dict[tuple[int, int], Segment],
    result: SliceResult,
) -> Path | None:
    """Диагностический PNG: контуры компонентов, границы слотов, номера ячеек.

    Ошибки алгоритма видны до экспорта: зелёный — крупные компоненты,
    оранжевый — мусор, красный — «слитый» (разрезан); номера исходных
    ячеек нарисованы растровыми цифрами (красный номер — пустая ячейка).
    """
    canvas = img.copy()
    painter = QPainter(canvas)
    try:
        row_tops: dict[int, int] = {}
        for row in sorted({seg.row for seg in segments.values()}):
            row_segs = [seg for seg in segments.values() if seg.row == row and seg.y0 >= 0]
            if row_segs:
                painter.setPen(QColor(255, 210, 0, 220))  # границы рядов — жёлтые
                top = min(s.y0 for s in row_segs) - 1
                row_tops[row] = top + 1
                painter.drawLine(0, top, result.sheet_w - 1, top)
        for seg in segments.values():
            painter.setPen(QColor(0, 200, 255, 220))  # границы слотов — голубые
            painter.drawLine(seg.slot_x0, 0, seg.slot_x0, result.sheet_h - 1)
            painter.drawLine(seg.slot_x1 + 1, 0, seg.slot_x1 + 1, result.sheet_h - 1)
        for comp in comps:
            if comp.split:
                color = QColor(255, 0, 0, 220)
            elif comp.major:
                color = QColor(0, 220, 0, 220)
            else:
                color = QColor(255, 140, 0, 220)
            painter.setPen(color)
            painter.drawRect(comp.x0, comp.y0, comp.x1 - comp.x0, comp.y1 - comp.y0)
        for seg in sorted(segments.values(), key=lambda s: s.source_index):
            color = QColor(0, 80, 255, 255)
            if not seg.pixels:
                color = QColor(255, 0, 0, 255)  # пустая ячейка — красный номер
            draw_number(
                painter, seg.slot_x0 + 3, row_tops.get(seg.row, 0) + 2, seg.source_index, color
            )
    finally:
        painter.end()
    diag_dir = OUT_ROOT / "_diagnostics"
    diag_dir.mkdir(parents=True, exist_ok=True)
    path = diag_dir / f"{plan.sheet.replace('/', '_')}.png"
    if not canvas.save(str(path)):
        result.warnings.append(f"не сохранился диагностический PNG: {path}")
        return None
    return path


def format_manifest(results: list[SliceResult]) -> str:
    """Сгенерировать clips.toml — спека воспроизведения (генерируется слайсером)."""
    lines = [
        "# clips.toml — playback-спека клипов малинки.",
        "# Генерируется scripts/slice_sheets.py; индексы кадров 0-based, включительно.",
        "#   sheet_cells    — позиция кадра → исходная ячейка шита (row-major)",
        "#   missing_cells  — пустые ячейки шита (кадры пропущены, нумерация не сжата)",
        "#   loop = [a, b]  — повторяемый сегмент (позиции записанных кадров)",
        "#   once = true    — один проход и завершение",
        "#   prefix_once    — кадры до loop сыграть один раз перед циклом",
        "#   suffix_on_exit — после loop доиграть хвост при выходе из состояния",
        "#   repeat_fill_ms — «несколько раз»: число повторов ~ заполнить цель (случайно)",
        "#   mirror = left  — loop-сегмент зеркалится (спрайт идёт влево)",
        "#   motion         — walk / traverse — движение окна во время клипа",
        "#   scale          — рантайм-масштаб (авто: эталон/медиана высот; ручной перезаписывает)",
        "",
    ]
    for res in results:
        plan = res.plan
        name = f"{plan.anim}/{plan.state}"
        lines.append(f'[clips."{name}"]')
        lines.append(f"frames = {res.frames_written}")
        if res.sheet_cells:
            cells = ", ".join(str(cell) for cell in res.sheet_cells)
            lines.append(f"sheet_cells = [{cells}]")
        if res.missing_cells:
            missing = ", ".join(str(cell) for cell in res.missing_cells)
            lines.append(f"missing_cells = [{missing}]")
        if plan.once:
            lines.append("once = true")
        loop = res.loop_positions or plan.loop
        if loop is not None:
            lines.append(f"loop = [{loop[0]}, {loop[1]}]")
        if plan.prefix_once:
            lines.append("prefix_once = true")
        if plan.suffix_on_exit:
            lines.append("suffix_on_exit = true")
        if plan.repeat_fill_ms is not None:
            lines.append(f"repeat_fill_ms = {plan.repeat_fill_ms}")
        if plan.mirror is not None:
            lines.append(f'mirror = "{plan.mirror}"')
        if plan.motion != "none":
            lines.append(f'motion = "{plan.motion}"')
        # ручной plan.scale (≠1.0) перезаписывает авто-масштаб нормализации
        scale = plan.scale if plan.scale != 1.0 else res.scale
        if scale != 1.0:
            lines.append(f"scale = {scale:.3f}")
        if plan.notes:
            lines.append(f"# {plan.notes}")
        lines.append("")
    return "\n".join(lines)


def main() -> int:
    app = QGuiApplication.instance() or QGuiApplication([])
    del app
    src_root = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_SRC
    if not src_root.is_dir():
        print(f"ОШИБКА: нет каталога шитов {src_root}", file=sys.stderr)
        return 1

    results: list[SliceResult] = []
    for plan in PLANS:
        # mirror-планы идут после источника в PLANS — зеркалим готовые кадры
        res = mirror_clip(plan) if plan.mirror_from else slice_sheet(plan, src_root)
        results.append(res)
        status = "OK" if not res.errors else "ОШИБКИ"
        cells = f"{res.rows}x{res.cols}" if res.rows else "-"
        missing = ", ".join(str(cell) for cell in res.missing_cells) or "нет"
        print(
            f"{plan.sheet:18} → {plan.anim}/{plan.state}: "
            f"{res.frames_written} кадров ({res.mode} {cells}), "
            f"пропуски: {missing}, scale={res.scale:.3f} [{status}]"
        )
        for warning in res.warnings:
            print(f"  предупреждение: {warning}")
        for error in res.errors:
            print(f"  ОШИБКА: {error}")

    # зеркальные клипы наследуют геометрию и scale источника (зеркало не меняет высоту)
    by_name = {f"{res.plan.anim}/{res.plan.state}": res for res in results}
    for res in results:
        source = res.plan.mirror_from
        if source is not None and source in by_name:
            res.content_h = by_name[source].content_h
            res.scale = by_name[source].scale
            res.sheet_cells = list(by_name[source].sheet_cells)
            res.missing_cells = list(by_name[source].missing_cells)
            if res.plan.loop is not None and res.sheet_cells:
                res.loop_positions = map_loop(res.plan.loop, res.sheet_cells, res)

    manifest_path = OUT_ROOT / "clips.toml"
    manifest_path.write_text(format_manifest(results), encoding="utf-8")
    print(f"\nМанифест: {manifest_path.relative_to(ROOT)}")
    print(f"Диагностика: {(OUT_ROOT / '_diagnostics').relative_to(ROOT)}/")
    total = sum(res.frames_written for res in results)
    print(f"Всего кадров: {total}")
    return 1 if any(res.errors for res in results) else 0


if __name__ == "__main__":
    raise SystemExit(main())
