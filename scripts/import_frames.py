#!/usr/bin/env python3
"""Импорт кадров в клип персонажа с авто-обновлением clips.toml.

Вход — каталог PNG: одиночные кадры ИЛИ ленты-полосы (несколько поз в ряд).
Ленты режутся ПО СОДЕРЖИМОМУ: профиль плотности столбцов по альфа-каналу,
деление слипшихся поз по «горлышкам» профиля, аварийный разрез аномально
широких блоков по медиане ширин соседних сегментов. Сетка и размер ячеек
не предполагаются — геометрия выводится из пикселей, параметры
сегментации вынесены в CLI.

Кадры пишутся как _NNN_DDD.png (ADR-005) в
<frames-root>/<Anim>/<State>/<Line>/; кроп по X-сегменту, по Y — полная
высота холста (композиция художника: земля, прыжки — сохраняются).
Секция clips.toml создаётся/обновляется автоматически: playback-флаги
сохраняются до явного переопределения, устаревшие поля шитов
(sheet_cells/missing_cells) и геометрические (loop/scale) сбрасываются
громко — их значения относились к прежним кадрам.

Пример:
    python scripts/import_frames.py --src ~/animation/ANGRY \\
        --clip "Angry/Normal" --duration 16 --expect 60 --scale 0.63
"""

from __future__ import annotations

import argparse
import logging
import os
import re
import statistics
import sys
import tomllib
from dataclasses import dataclass
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QImage

logger = logging.getLogger("import_frames")

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_FRAMES_ROOT = REPO_ROOT / "assets" / "characters" / "malinka"

# playback-поля секции: сохраняются из старой секции, если не заданы в CLI
PLAYBACK_FIELDS = ("once", "prefix_once", "suffix_on_exit", "repeat_fill_ms", "mirror", "motion")
# относились к шитам — при импорте кадров не имеют смысла
STALE_FIELDS = ("sheet_cells", "missing_cells")


@dataclass(frozen=True, slots=True)
class Segment:
    """X-диапазон кадра в ленте (границы включительно)."""

    x0: int
    x1: int

    @property
    def width(self) -> int:
        return self.x1 - self.x0 + 1


def numeric_key(path: Path) -> tuple[int, str]:
    """Числовой порядок файлов: 2.png < 10.png (лексикографический — нет)."""
    match = re.search(r"\d+", path.stem)
    if match is None:
        raise ValueError(f"в имени файла {path.name} нет числа — порядок не определить")
    return int(match.group()), path.name


def column_density(img: QImage, alpha_threshold: int) -> list[int]:
    """Плотность столбцов: сколько пикселей столбца с alpha >= порога."""
    rgba = img.convertToFormat(QImage.Format.Format_RGBA8888)
    width, height, stride = rgba.width(), rgba.height(), rgba.bytesPerLine()
    bits = rgba.constBits()
    view = bits if isinstance(bits, memoryview) else memoryview(bits)
    dens = [0] * width
    for y in range(height):
        base = y * stride
        alphas = bytes(view[base : base + width * 4])[3::4]
        dens = [d + (a >= alpha_threshold) for d, a in zip(dens, alphas, strict=True)]
    return dens


def occupied_runs(dens: list[int], min_col_opaque: int) -> list[tuple[int, int]]:
    """Прогоны занятых столбцов (границы включительно) с плотностью >= порога."""
    runs: list[tuple[int, int]] = []
    start: int | None = None
    for i in range(len(dens) + 1):
        occupied = i < len(dens) and dens[i] >= min_col_opaque
        if occupied and start is None:
            start = i
        elif not occupied and start is not None:
            runs.append((start, i - 1))
            start = None
    return runs


def neck_split(
    dens: list[int],
    seg: tuple[int, int],
    neck_window: int,
    neck_ratio: float,
    min_frame_px: int,
) -> list[tuple[int, int]]:
    """Рекурсивное деление слипшихся блоков по «горлышкам» профиля плотности.

    Горлышко — участок, где скользящее среднее плотности падает ниже
    neck_ratio × среднего по блоку; разрез — в самом глубоком минимуме
    (столбец разреза отбрасывается). Куски короче 2 × min_frame_px не режутся.
    """
    x0, x1 = seg
    width = x1 - x0 + 1
    if width < 2 * min_frame_px:
        return [seg]
    prof = dens[x0 : x1 + 1]
    half = max(1, neck_window // 2)

    def window(i: int) -> list[int]:
        return prof[max(0, i - half) : i + half + 1]

    smooth = [sum(window(i)) / len(window(i)) for i in range(len(prof))]
    thresh = neck_ratio * (sum(smooth) / len(smooth))
    candidates = [
        i
        for i in range(1, len(smooth) - 1)
        if smooth[i] <= thresh
        and smooth[i] <= smooth[i - 1]
        and smooth[i] <= smooth[i + 1]
        and i >= min_frame_px
        and len(prof) - (i + 1) >= min_frame_px
    ]
    if not candidates:
        return [seg]
    best = min(candidates, key=lambda i: sum(window(i)))
    cut = x0 + best
    return neck_split(dens, (x0, cut - 1), neck_window, neck_ratio, min_frame_px) + neck_split(
        dens, (cut + 1, x1), neck_window, neck_ratio, min_frame_px
    )


def emergency_split(
    dens: list[int], segs: list[tuple[int, int]], max_frame_ratio: float
) -> list[tuple[int, int]]:
    """Аварийный разрез блоков, где слиплись позы без выраженного горлышка.

    Ориентир — медиана ширин сегментов файла; блок шире
    max_frame_ratio × медианы делится на round(ширина/медиана) частей
    разрезами в минимумах профиля, ближайших к равным долям. Один сегмент
    на файл — сравнивать не с чем, деления нет.
    """
    if max_frame_ratio <= 0 or len(segs) < 2:
        return segs
    med = float(statistics.median(x1 - x0 + 1 for x0, x1 in segs))
    if med <= 0:
        return segs
    out: list[tuple[int, int]] = []
    for x0, x1 in segs:
        width = x1 - x0 + 1
        parts = round(width / med)
        if width <= max_frame_ratio * med or parts < 2:
            out.append((x0, x1))
            continue
        prof = dens[x0 : x1 + 1]
        cuts: list[int] = []
        for i in range(1, parts):
            target = round(i * width / parts)
            span = max(1, width // (2 * parts))
            lo, hi = max(0, target - span), min(len(prof), target + span + 1)
            best = min(range(lo, hi), key=lambda j: (prof[j], abs(j - target)))
            cuts.append(x0 + best)
        cuts = sorted(set(cuts))
        logger.warning(
            "аварийный разрез: блок x=[%d..%d] w=%d > %.2f × медианы %.0f — на %d части",
            x0,
            x1,
            width,
            max_frame_ratio,
            med,
            len(cuts) + 1,
        )
        prev = x0
        for cut in cuts:
            if cut - 1 >= prev:
                out.append((prev, cut - 1))
            prev = cut
        if x1 >= prev:
            out.append((prev, x1))
    out.sort()
    return out


def segment_strip(img: QImage, args: argparse.Namespace) -> list[Segment]:
    """Разрезать ленту на кадры по содержимому (не лента — один кадр)."""
    dens = column_density(img, args.alpha_threshold)
    kept: list[tuple[int, int]] = []
    for x0, x1 in occupied_runs(dens, args.min_col_opaque):
        if x1 - x0 + 1 >= args.min_frame_px:
            kept.append((x0, x1))
        else:
            logger.warning(
                "шум: прогон x=[%d..%d] w=%d < min-frame-px=%d — отброшен",
                x0,
                x1,
                x1 - x0 + 1,
                args.min_frame_px,
            )
    split: list[tuple[int, int]] = []
    for run in kept:
        split.extend(neck_split(dens, run, args.neck_window, args.neck_ratio, args.min_frame_px))
    split = emergency_split(dens, split, args.max_frame_ratio)
    return [Segment(x0, x1) for x0, x1 in split]


def build_section(name: str, frames: int, playback: dict[str, object]) -> str:
    """Текст секции [clips."..."] в формате slice_sheets.format_manifest."""
    lines = [f'[clips."{name}"]', f"frames = {frames}"]
    if playback.get("once"):
        lines.append("once = true")
    loop = playback.get("loop")
    if loop is not None:
        lines.append(f"loop = [{loop[0]}, {loop[1]}]")  # type: ignore[index]
    if playback.get("prefix_once"):
        lines.append("prefix_once = true")
    if playback.get("suffix_on_exit"):
        lines.append("suffix_on_exit = true")
    if playback.get("repeat_fill_ms") is not None:
        lines.append(f"repeat_fill_ms = {playback['repeat_fill_ms']}")
    if playback.get("mirror") is not None:
        lines.append(f'mirror = "{playback["mirror"]}"')
    if playback.get("motion") not in (None, "none"):
        lines.append(f'motion = "{playback["motion"]}"')
    if playback.get("clip_scale") is not None:
        lines.append(f"scale = {float(playback['clip_scale']):.3f}")
    return "\n".join(lines)


def replace_section(text: str, name: str, block: str) -> str:
    """Заменить секцию [clips."name"] или дописать её в конец файла."""
    header = f'[clips."{name}"]'
    lines = text.splitlines()
    start = next((i for i, line in enumerate(lines) if line.strip() == header), None)
    if start is None:
        body = text.rstrip("\n")
        return (body + "\n\n" if body else "") + block + "\n"
    end = len(lines)
    for j in range(start + 1, len(lines)):
        if lines[j].lstrip().startswith("["):
            end = j
            break
    new_lines = lines[:start] + block.splitlines() + [""] + lines[end:]
    return "\n".join(new_lines).rstrip("\n") + "\n"


def update_manifest(path: Path, name: str, frames: int, cli: dict[str, object]) -> None:
    """Создать/обновить секцию клипа; устаревшие поля сбрасываются громко."""
    old_text = path.read_text(encoding="utf-8") if path.is_file() else ""
    old: dict[object, object] = {}
    if old_text:
        try:
            found = tomllib.loads(old_text).get("clips", {}).get(name)
            old = found if isinstance(found, dict) else {}
        except tomllib.TOMLDecodeError as error:
            logger.warning("clips.toml не разбирается (%s) — секция будет перезаписана", error)

    playback: dict[str, object] = {}
    preserved: list[str] = []
    for field_name in PLAYBACK_FIELDS:
        value = cli.get(field_name)
        if value is not None and value is not False:
            playback[field_name] = value
        elif field_name in old:
            playback[field_name] = old[field_name]
            preserved.append(f"{field_name}={old[field_name]!r}")
    if preserved:
        logger.info("секция %r: playback-поля сохранены: %s", name, ", ".join(preserved))

    loop = cli.get("loop")
    if loop is not None:
        playback["loop"] = loop
        if playback.pop("once", False):
            logger.warning("секция %r: once=true конфликтует с --loop — once сброшен", name)
    elif "loop" in old:
        logger.warning(
            "секция %r: старый loop=%r сброшен — индексы относились к прежним кадрам",
            name,
            old["loop"],
        )
    for field_name in STALE_FIELDS:
        if field_name in old:
            logger.warning(
                "секция %r: поле %s=%r относилось к шитам — сброшено при импорте кадров",
                name,
                field_name,
                old[field_name],
            )
    if "scale" in old and cli.get("clip_scale") is None:
        logger.warning(
            "секция %r: старый scale=%r сброшен — размеры кадров изменились", name, old["scale"]
        )
    if cli.get("clip_scale") is not None:
        playback["clip_scale"] = cli["clip_scale"]

    block = build_section(name, frames, playback)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(replace_section(old_text, name, block), encoding="utf-8")
    logger.info("секция %r обновлена: frames=%d → %s", name, frames, path)


def parse_loop(value: str) -> tuple[int, int]:
    """`A:B` → (A, B) включительно; не пара целых — ошибка аргумента."""
    match = re.fullmatch(r"(\d+)\s*:\s*(\d+)", value.strip())
    if match is None:
        raise argparse.ArgumentTypeError(f"loop вида A:B, например 0:5 — получено {value!r}")
    left, right = int(match.group(1)), int(match.group(2))
    if left > right:
        raise argparse.ArgumentTypeError(f"loop: {left} > {right}")
    return left, right


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Разобрать аргументы командной строки."""
    parser = argparse.ArgumentParser(
        description="Импорт кадров (одиночных или лент) в клип с авто-обновлением clips.toml.",
    )
    parser.add_argument("--src", type=Path, required=True, help="каталог PNG: кадры или ленты")
    parser.add_argument(
        "--clip", required=True, help='имя клипа "Anim/State", напр. "Angry/Normal"'
    )
    parser.add_argument("--line", type=int, default=1, help="линия анимации 1..99 (1)")
    parser.add_argument("--frames-root", type=Path, default=DEFAULT_FRAMES_ROOT)
    parser.add_argument(
        "--manifest", type=Path, default=None, help="clips.toml (frames-root/clips.toml)"
    )
    durations = parser.add_mutually_exclusive_group(required=True)
    durations.add_argument("--duration", type=int, help="единая длительность кадра, мс")
    durations.add_argument("--durations", help="длительности кадров через запятую, мс")
    segmentation = parser.add_argument_group("сегментация лент (по содержимому)")
    segmentation.add_argument("--alpha-threshold", type=int, default=1, help="alpha >= порога (1)")
    segmentation.add_argument(
        "--min-col-opaque", type=int, default=2, help="плотность занятого столбца (2)"
    )
    segmentation.add_argument(
        "--min-frame-px", type=int, default=100, help="минимальная ширина кадра (100)"
    )
    segmentation.add_argument(
        "--neck-window", type=int, default=15, help="окно скользящего среднего (15)"
    )
    segmentation.add_argument(
        "--neck-ratio", type=float, default=0.25, help="порог горлышка от среднего (0.25)"
    )
    segmentation.add_argument(
        "--max-frame-ratio", type=float, default=1.6, help="порог аварийного разреза (1.6)"
    )
    output = parser.add_argument_group("вывод кадров")
    output.add_argument("--scale", type=float, default=1.0, help="офлайн-масштаб кадров (1.0)")
    output.add_argument("--pad", type=int, default=0, help="отступ по X вокруг сегмента, px (0)")
    output.add_argument(
        "--expect", type=int, default=None, help="ожидаемое число кадров — расхождение = ошибка"
    )
    playback = parser.add_argument_group("playback-флаги секции clips.toml")
    playback.add_argument("--once", action="store_true", help="один проход и завершение")
    playback.add_argument(
        "--loop", type=parse_loop, metavar="A:B", help="повторяемый сегмент, включительно"
    )
    playback.add_argument("--prefix-once", action="store_true", dest="prefix_once")
    playback.add_argument("--suffix-on-exit", action="store_true", dest="suffix_on_exit")
    playback.add_argument("--repeat-fill-ms", type=int, dest="repeat_fill_ms")
    playback.add_argument("--mirror", choices=("left", "right"), help="loop-сегмент зеркалится")
    playback.add_argument("--motion", choices=("walk", "traverse", "none"))
    playback.add_argument(
        "--clip-scale", type=float, dest="clip_scale", help="scale в секции (рантайм-масштаб)"
    )
    return parser.parse_args(argv)


def resolve_durations(args: argparse.Namespace, total: int) -> list[int] | None:
    """Длительности всех кадров, мс; None — ошибка аргументов (уже залогирована)."""
    if args.durations is not None:
        try:
            values = [int(item.strip()) for item in args.durations.split(",") if item.strip()]
        except ValueError:
            logger.error("--durations: ожидались целые через запятую, получено %r", args.durations)
            return None
        if len(values) != total:
            logger.error("--durations: %d значений при %d кадрах", len(values), total)
            return None
        if any(value <= 0 for value in values):
            logger.error("--durations: длительности должны быть положительными")
            return None
        return values
    if args.duration <= 0:
        logger.error("--duration должен быть положительным, получено %d", args.duration)
        return None
    return [args.duration] * total


def run(args: argparse.Namespace) -> int:
    """Импорт: сегментация, запись кадров, обновление clips.toml. 0 — успех."""
    if not args.src.is_dir():
        logger.error("каталог-источник не найден: %s", args.src)
        return 2
    parts = args.clip.split("/")
    if len(parts) != 2 or not all(part.strip() for part in parts):
        logger.error('--clip должен быть вида "Anim/State", получено %r', args.clip)
        return 2
    if not 1 <= args.line <= 99:
        logger.error("--line должен быть 1..99, получено %d", args.line)
        return 2
    if args.once and args.loop is not None:
        logger.error("--once и --loop несовместимы")
        return 2

    files = [p for p in args.src.iterdir() if p.suffix.lower() == ".png"]
    if not files:
        logger.error("в %s нет PNG-файлов", args.src)
        return 2
    try:
        files.sort(key=numeric_key)
    except ValueError as error:
        logger.error("%s", error)
        return 2

    # проход 1: сегментация и контроль — до записи файлов
    planned: list[tuple[Path, list[Segment]]] = []
    for path in files:
        img = QImage(str(path))
        if img.isNull():
            logger.error("не удалось прочитать %s", path)
            return 2
        segments = segment_strip(img, args)
        logger.info(
            "%s: %d кадр(ов) %s",
            path.name,
            len(segments),
            ", ".join(f"[{s.x0}..{s.x1}] w={s.width}" for s in segments),
        )
        if not segments:
            logger.error("%s: не найдено ни одного сегмента (проверьте пороги)", path)
            return 2
        planned.append((path, segments))
    total = sum(len(segments) for _, segments in planned)

    if args.expect is not None and total != args.expect:
        logger.error(
            "ожидалось %d кадров, получено %d — расхождение сегментации", args.expect, total
        )
        return 2
    durations = resolve_durations(args, total)
    if durations is None:
        return 2
    if args.loop is not None and args.loop[1] >= total:
        logger.error("loop=%r выходит за пределы %d кадров", list(args.loop), total)
        return 2

    dst_dir = args.frames_root / parts[0] / parts[1] / str(args.line)
    dst_dir.mkdir(parents=True, exist_ok=True)
    removed = 0
    for old_frame in dst_dir.glob("_*.png"):
        old_frame.unlink()
        removed += 1
    if removed:
        logger.info("старые кадры удалены: %d (%s)", removed, dst_dir)

    index = 0
    for path, segments in planned:
        img = QImage(str(path))
        for segment in segments:
            x0 = max(0, segment.x0 - args.pad)
            x1 = min(img.width() - 1, segment.x1 + args.pad)
            frame = img.copy(x0, 0, x1 - x0 + 1, img.height())
            if args.scale != 1.0:
                frame = frame.scaled(
                    max(1, round(frame.width() * args.scale)),
                    max(1, round(frame.height() * args.scale)),
                    Qt.AspectRatioMode.IgnoreAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                )
            out = dst_dir / f"_{index:03d}_{durations[index]:03d}.png"
            if not frame.save(str(out), "PNG"):
                logger.error("не удалось сохранить %s", out)
                return 2
            index += 1

    update_manifest(
        args.manifest if args.manifest is not None else args.frames_root / "clips.toml",
        args.clip,
        total,
        {
            "once": args.once or None,
            "prefix_once": args.prefix_once or None,
            "suffix_on_exit": args.suffix_on_exit or None,
            "repeat_fill_ms": args.repeat_fill_ms,
            "mirror": args.mirror,
            "motion": args.motion,
            "loop": args.loop,
            "clip_scale": args.clip_scale,
        },
    )
    logger.info("готово: %d кадров → %s", total, dst_dir)
    return 0


def main() -> int:
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    return run(parse_args())


if __name__ == "__main__":
    sys.exit(main())