"""Нарезка готовых шитов девочки-малинки → assets/characters/malinka/ (PHASE 4).

Источник: каталог /home/fake-cat/projects/animation/<ШИТ>/sheet.png (17 шитов).
Шиты — сетки (6×2, у LIE DORMANT 5×2), но реальный контент расходится с
равномерной сеткой: кроссоверы заходят в соседние ячейки, колонки смещены.
Кадры ищутся связными компонентами alpha-маски всего шита: равномерная сетка
служит только распределителем компонентов по кадрам (по центру компонента),
кроп идёт по bbox компонента целиком — линии сетки контент не режут. Мелкие
сколы фона (< MIN_COMPONENT_PX) не расширяют bbox кадра.

Якорь каждого кадра — «низ + центр по X» на едином холсте 296×471, 1:1 (без
масштабирования): bbox контента кадра кладётся по центру и вплотную к низу
холста — общий пол гарантируется у всех кадров. Контент кадра шире/выше холста
уменьшается ровно до влезания (с предупреждением). Ячейка без компонентов —
фолбэк на alpha-bbox самой ячейки (с предупреждением).

Результат: assets/characters/malinka/<Анимация>/<Состояние>/1/_NNN_DDD.png
плюс манифест assets/characters/malinka/clips.toml со спекой воспроизведения
(loop-диапазоны 0-based включительно, повторы, зеркало, масштаб, движение).
Клип с `mirror_from` не режется из шита, а зеркально отражается (по X) из уже
нарезанного клипа — так получается ходьба влево (Walk/Left = отражение
Walk/Right) без отдельного шита-источника.

Запуск (с любой директории):
    .venv/bin/python scripts/slice_sheets.py [ИСХОДНЫЙ_КАТАЛОГ]
"""

from __future__ import annotations

import os
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

CANVAS_W, CANVAS_H = 296, 471  # единый холст всех кадров
ALPHA_THRESHOLD = 64
# Компоненты меньше порога — пиксельные сколы фона; легитимные частицы крупнее
# (искры ANGRY — 33..623 px, остальные шиты — мусор <= 84 px, но он сидит внутри
# bbox спрайтов и на кадр не влияет; TYPING/ERROR_PANIC — 1..4 px снаружи).
MIN_COMPONENT_PX = 10


@dataclass(frozen=True, slots=True)
class ClipPlan:
    """План нарезки одного шита: имя клипа, сетка, длительность, спека."""

    sheet: str  # каталог-источник (имя шита в animation/)
    anim: str  # каталог «Анимация» (префикс состояний FSM)
    state: str  # каталог «Состояние»
    duration_ms: int  # длительность кадра в имени _NNN_DDD.png
    cols: int = 6
    rows: int = 2
    # --- playback-спека (0-based, включительно; None → без уточнений) ---
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


# Шит → клип. Длительности — по характеру движения (старый план slice_malinka).
PLANS: tuple[ClipPlan, ...] = (
    ClipPlan("ANGRY", "Angry", "Normal", 100, loop=(4, 10), repeat_fill_ms=4000),
    ClipPlan("COFFEE", "Coffee", "Normal", 200, loop=(1, 9)),
    ClipPlan("DANCING", "Dance", "Normal", 120, loop=(2, 10)),
    ClipPlan("ERROR_PANIC", "Error", "Panic", 100, once=True),
    ClipPlan("HAPPY_SUCCESS", "Happy", "Success", 120, once=True),
    # Движение окна только у ходьбы (решение пользователя): остальные клипы статичны
    ClipPlan("HIDE OUT", "Hide", "Out", 150, once=True),
    ClipPlan("IDLE", "Idle", "Normal", 150, once=True),
    ClipPlan("LIE DORMANT", "Lie", "Dormant", 300, once=True, cols=5),
    # Переходный клип: каждая смена анимации начинается с него (player.set_transition)
    ClipPlan("MOVED CLIP", "Move", "Transition", 100, once=True),
    ClipPlan("SITTING HAPPILLY", "Sit", "Happily", 250, loop=(3, 11)),
    ClipPlan("SIT_SLEEP_WAKE", "Sleep", "Wake", 250, loop=(4, 9), suffix_on_exit=True),
    ClipPlan("TALKING", "Talk", "Normal", 150, loop=(0, 11)),
    ClipPlan("THINKING", "Thinking", "Normal", 200, once=True),
    ClipPlan("TYPING", "Sit", "Typing", 250, loop=(1, 10)),
    ClipPlan("WALK BACK", "Walk", "Back", 120, loop=(6, 10), motion="walk"),
    ClipPlan("WALK DIRECT", "Walk", "Direct", 120, loop=(2, 10), mirror="left", motion="walk"),
    ClipPlan(
        "WALK RIGHT",
        "Walk",
        "Right",
        120,
        loop=(2, 10),
        motion="walk",
        notes="спрайт мельче остальных (h≈330) — scale подбирается визуально",
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
    ClipPlan("WELCOME", "Welcome", "Greeting", 150, once=True),
)


@dataclass(slots=True)
class SliceResult:
    """Итог нарезки одного шита."""

    plan: ClipPlan
    sheet_w: int = 0
    sheet_h: int = 0
    frames_written: int = 0
    scale: float = 1.0
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


def alpha_bbox(image: QImage) -> tuple[int, int, int, int] | None:
    """bbox контента с alpha>=порога; None — изображение пустое."""
    image = image.convertToFormat(QImage.Format.Format_RGBA8888)
    data = bytes(image.constBits())
    stride = image.bytesPerLine()
    x0, y0, x1, y1 = image.width(), image.height(), -1, -1
    for y in range(image.height()):
        row = y * stride
        for x in range(image.width()):
            if data[row + x * 4 + 3] >= ALPHA_THRESHOLD:
                x0 = min(x0, x)
                x1 = max(x1, x)
                y0 = min(y0, y)
                y1 = max(y1, y)
    if x1 < 0:
        return None
    return x0, y0, x1, y1


def connected_components(img: QImage) -> list[tuple[int, int, int, int, int]]:
    """Связные компоненты alpha-маски (4-связность) всего изображения.

    Возвращает [(area, x0, y0, x1, y1)] — bbox в координатах изображения
    (включительно). Контент — пиксели с alpha >= ALPHA_THRESHOLD.
    """
    rgba = img.convertToFormat(QImage.Format.Format_RGBA8888)
    data = bytes(rgba.constBits())
    stride = rgba.bytesPerLine()
    w, h = rgba.width(), rgba.height()
    mask = bytearray(w * h)
    for y in range(h):
        row = y * stride
        base = y * w
        for x in range(w):
            if data[row + x * 4 + 3] >= ALPHA_THRESHOLD:
                mask[base + x] = 1
    out: list[tuple[int, int, int, int, int]] = []
    seen = bytearray(w * h)
    for start in range(w * h):
        if not mask[start] or seen[start]:
            continue
        queue: deque[int] = deque([start])
        seen[start] = 1
        area = 0
        x0 = y0 = w + h
        x1 = y1 = -1
        while queue:
            p = queue.popleft()
            area += 1
            px, py = p % w, p // w
            x0 = min(x0, px)
            x1 = max(x1, px)
            y0 = min(y0, py)
            y1 = max(y1, py)
            if px > 0 and mask[p - 1] and not seen[p - 1]:
                seen[p - 1] = 1
                queue.append(p - 1)
            if px < w - 1 and mask[p + 1] and not seen[p + 1]:
                seen[p + 1] = 1
                queue.append(p + 1)
            if py > 0 and mask[p - w] and not seen[p - w]:
                seen[p - w] = 1
                queue.append(p - w)
            if py < h - 1 and mask[p + w] and not seen[p + w]:
                seen[p + w] = 1
                queue.append(p + w)
        out.append((area, x0, y0, x1, y1))
    return out


def uniform_bounds(length: int, parts: int) -> list[int]:
    """Границы равномерной сетки: [0, середины..., length]."""
    step = length / parts
    bounds = [round(i * step) for i in range(parts + 1)]
    bounds[0], bounds[-1] = 0, length
    return bounds


def cell_components(
    comps: list[tuple[int, int, int, int, int]],
    *,
    xbounds: list[int],
    ybounds: list[int],
) -> list[list[tuple[int, int, int, int, int]]]:
    """Разложить компоненты по ячейкам сетки по центру компонента.

    Компонент целиком (весь bbox, даже если выходит за границы ячейки)
    достаётся ячейке, содержащей его центр, — кроссовер не режется, а чужие
    пиксели в своей ячейке не расширяют bbox кадра.
    """
    cols, rows = len(xbounds) - 1, len(ybounds) - 1
    cells: list[list[tuple[int, int, int, int, int]]] = [[] for _ in range(cols * rows)]
    for comp in comps:
        _, bx0, by0, bx1, by1 = comp
        col = next((i for i in range(cols) if bx0 + bx1 < 2 * xbounds[i + 1]), cols - 1)
        row = next((i for i in range(rows) if by0 + by1 < 2 * ybounds[i + 1]), rows - 1)
        cells[row * cols + col].append(comp)
    return cells


def slice_sheet(plan: ClipPlan, src_root: Path) -> SliceResult:
    """Нарезать один шит: компоненты контента → единый холст → PNG + метаданные."""
    sheet_path = src_root / plan.sheet / "sheet.png"
    result = SliceResult(plan=plan, sheet_w=0, sheet_h=0)
    img = QImage(str(sheet_path))
    if img.isNull():
        result.errors.append(f"не удалось открыть {sheet_path}")
        return result
    img = img.convertToFormat(QImage.Format.Format_RGBA8888)
    result.sheet_w, result.sheet_h = img.width(), img.height()

    # Компоненты контента (без сколов фона) → ячейки равномерной сетки по центру
    comps = [comp for comp in connected_components(img) if comp[0] >= MIN_COMPONENT_PX]
    xbounds = uniform_bounds(img.width(), plan.cols)
    ybounds = uniform_bounds(img.height(), plan.rows)
    cells = cell_components(comps, xbounds=xbounds, ybounds=ybounds)

    line_dir = OUT_ROOT / plan.anim / plan.state / "1"
    line_dir.mkdir(parents=True, exist_ok=True)
    for old in line_dir.glob("_*.png"):  # идемпотентный перезапуск
        old.unlink()

    # Проход 1: bbox каждого кадра — компоненты ячейки или фолбэк на ячейку
    frame_bboxes: list[tuple[int, int, int, int] | None] = []
    for row in range(plan.rows):
        for col in range(plan.cols):
            x0, x1 = xbounds[col], xbounds[col + 1]
            y0, y1 = ybounds[row], ybounds[row + 1]
            index = row * plan.cols + col
            tag = f"{plan.anim}/{plan.state} кадр {index}"
            members = cells[index]
            if members:
                bbox: tuple[int, int, int, int] | None = (
                    min(comp[1] for comp in members),
                    min(comp[2] for comp in members),
                    max(comp[3] for comp in members),
                    max(comp[4] for comp in members),
                )
            else:
                # Фолбэк: bbox контента самой ячейки (компонентов нет/все мельче порога)
                cell_bbox = alpha_bbox(img.copy(x0, y0, x1 - x0, y1 - y0))
                if cell_bbox is None:
                    result.warnings.append(
                        f"ячейка без пикселей — кадр пропущен: {tag} (x{x0}..{x1} y{y0}..{y1})"
                    )
                    bbox = None
                else:
                    result.warnings.append(
                        f"нет компонентов — фолбэк на ячейку: {tag} (x{x0}..{x1} y{y0}..{y1})"
                    )
                    bbox = (
                        x0 + cell_bbox[0],
                        y0 + cell_bbox[1],
                        x0 + cell_bbox[2],
                        y0 + cell_bbox[3],
                    )
            if bbox is not None:
                bx0, by0, bx1, by1 = bbox
                if bx0 == 0 or by0 == 0 or bx1 == img.width() - 1 or by1 == img.height() - 1:
                    result.warnings.append(
                        f"контент касается края шита: {tag} bbox={bbox} "
                        f"лист={img.width()}x{img.height()} (возможен обрез)"
                    )
            frame_bboxes.append(bbox)

    # Проход 2: якорь «низ + центр по X» каждого кадра — 1:1 на общем холсте
    used = [bbox for bbox in frame_bboxes if bbox is not None]
    if not used:
        result.errors.append(f"в шите {plan.sheet} нет ни одного кадра с контентом")
        return result

    for index, bbox in enumerate(frame_bboxes):
        if bbox is None:
            continue
        bx0, by0, bx1, by1 = bbox
        bw, bh = bx1 - bx0 + 1, by1 - by0 + 1
        # single-frame scale: только если контент кадра не влезает в холст
        frame_scale = 1.0
        if bw > CANVAS_W or bh > CANVAS_H:
            frame_scale = min(CANVAS_W / bw, CANVAS_H / bh)
            result.warnings.append(
                f"контент кадра больше холста: {plan.anim}/{plan.state} кадр {index} "
                f"{bw}x{bh} → scale={frame_scale:.3f}"
            )
        dst_w = max(1, int(round(bw * frame_scale)))
        dst_h = max(1, int(round(bh * frame_scale)))
        cropped = img.copy(bx0, by0, bw, bh)
        if frame_scale < 1.0:
            cropped = cropped.scaled(
                dst_w,
                dst_h,
                Qt.AspectRatioMode.IgnoreAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
        dst_x = int(round((CANVAS_W - dst_w) / 2))
        dst_y = CANVAS_H - dst_h
        canvas = QImage(CANVAS_W, CANVAS_H, QImage.Format.Format_RGBA8888)
        canvas.fill(QColor(0, 0, 0, 0))
        painter = QPainter(canvas)
        painter.drawImage(dst_x, dst_y, cropped)
        painter.end()
        path = line_dir / f"_{index:03d}_{plan.duration_ms}.png"
        if not canvas.save(str(path)):
            result.errors.append(f"не сохранился: {path}")
            continue
        result.frames_written += 1

    result.scale = 1.0  # кадры кладутся 1:1 (якорь «низ + центр по X»)
    total = plan.cols * plan.rows
    if plan.loop is not None:
        lo, hi = plan.loop
        if not (0 <= lo <= hi < total):
            result.errors.append(f"loop {plan.loop} вне диапазона кадров 0..{total - 1}")
    return result


def mirror_clip(plan: ClipPlan) -> SliceResult:
    """Зеркально отразить по X уже нарезанный клип (plan.mirror_from) → новый клип.

    Используется для ходьбы влево: Walk/Left = отражение Walk/Right — отдельного
    шита-источника нет. Имена кадров и длительности сохраняются; отражение по X
    не трогает высоту и нижнюю границу, поэтому общий пол холста остаётся.
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


def format_manifest(results: list[SliceResult]) -> str:
    """Сгенерировать clips.toml — спека воспроизведения (генерируется слайсером)."""
    lines = [
        "# clips.toml — playback-спека клипов малинки.",
        "# Генерируется scripts/slice_sheets.py; индексы кадров 0-based, включительно.",
        "#   loop = [a, b]  — повторяемый сегмент (без него — весь клип / once)",
        "#   once = true    — один проход и завершение",
        "#   prefix_once    — кадры до loop сыграть один раз перед циклом",
        "#   suffix_on_exit — после loop доиграть хвост при выходе из состояния",
        "#   repeat_fill_ms — «несколько раз»: число повторов ~ заполнить цель (случайно)",
        "#   mirror = left  — loop-сегмент зеркалится (спрайт идёт влево)",
        "#   motion         — walk / traverse — движение окна во время клипа",
        "#   scale          — рантайм-масштаб (1.0 — без изменений)",
        "",
    ]
    for res in results:
        plan = res.plan
        name = f"{plan.anim}/{plan.state}"
        lines.append(f'[clips."{name}"]')
        lines.append(f"frames = {plan.cols * plan.rows}")
        if plan.once:
            lines.append("once = true")
        if plan.loop is not None:
            lines.append(f"loop = [{plan.loop[0]}, {plan.loop[1]}]")
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
        scale = min(res.scale, plan.scale)
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
        print(
            f"{plan.sheet:18} → {plan.anim}/{plan.state}: "
            f"{res.frames_written}/{plan.cols * plan.rows} кадров, "
            f"лист {res.sheet_w}x{res.sheet_h}, scale={res.scale:.3f} [{status}]"
        )
        for warning in res.warnings:
            print(f"  предупреждение: {warning}")
        for error in res.errors:
            print(f"  ОШИБКА: {error}")

    manifest_path = OUT_ROOT / "clips.toml"
    manifest_path.write_text(format_manifest(results), encoding="utf-8")
    print(f"\nМанифест: {manifest_path.relative_to(ROOT)}")
    total = sum(res.frames_written for res in results)
    print(f"Всего кадров: {total}")
    return 1 if any(res.errors for res in results) else 0


if __name__ == "__main__":
    raise SystemExit(main())
