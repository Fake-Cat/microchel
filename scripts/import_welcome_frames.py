"""Конвертация кадров приветственной крутки в клип Welcome малинки (ADR-005).

Источник: assets/frames/frame_*.png (1024×1024, RGBA; пропуски номеров допустимы).
Результат: assets/characters/malinka/Welcome/Normal/1/_NNN_DDD.png — приветствие
крутится бесконечно, пока у персонажа нет других клипов (idle-фоллбэк окна).

Все кадры приводятся к общему прямоугольнику: сначала масштабируется весь холст,
затем берётся объединение bbox по alpha≥64 всех кадров (+отступ) и кроп — размер
окна одинаков во всех кадрах, персонаж не «прыгает» при смене кадра.

Материал пользовательский; масштаб и длительность задаются флагами.

Запуск: .venv/bin/python scripts/import_welcome_frames.py [--scale 0.25] [--duration 100]
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

from PySide6.QtCore import QRect, Qt
from PySide6.QtGui import QImage

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SRC = ROOT / "assets" / "frames"
DEFAULT_DST = ROOT / "assets" / "characters" / "malinka" / "Welcome" / "Normal" / "1"
ALPHA_THRESHOLD = 64
PAD_PX = 4  # отступ вокруг объединённого bbox (в пикселях результата)


def source_frames(src: Path) -> list[Path]:
    """Кадры frame_*.png, отсортированные по номеру (пропуски номеров допустимы)."""
    frames = list(src.glob("frame_*.png"))
    frames.sort(key=lambda path: int(re.search(r"(\d+)$", path.stem).group(1)))
    return frames


def frame_bbox(image: QImage) -> QRect | None:
    """Прямоугольник пикселей с alpha≥64; None — пустой кадр."""
    data = bytes(image.constBits())
    stride = image.bytesPerLine()
    x0, y0, x1, y1 = image.width(), image.height(), -1, -1
    for y in range(image.height()):
        row = data[y * stride : (y + 1) * stride][3::4]  # только alpha-канал RGBA
        hit = False
        for x, alpha in enumerate(row):
            if alpha >= ALPHA_THRESHOLD:
                hit = True
                x0 = min(x0, x)
                x1 = max(x1, x)
        if hit:
            y0 = min(y0, y)
            y1 = max(y1, y)
    if x1 < 0:
        return None
    return QRect(x0, y0, x1 - x0 + 1, y1 - y0 + 1)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Кадры приветствия → клип Welcome")
    parser.add_argument("--src", type=Path, default=DEFAULT_SRC, help="каталог frame_*.png")
    parser.add_argument("--dst", type=Path, default=DEFAULT_DST, help="каталог линии клипа")
    parser.add_argument("--scale", type=float, default=0.25, help="масштаб холста (0..1]")
    parser.add_argument(
        "--duration", type=int, default=100, metavar="MS", help="длительность кадра, мс"
    )
    args = parser.parse_args(argv)
    if not 0 < args.scale <= 1:
        parser.error("--scale должен быть в (0, 1]")
    if args.duration <= 0:
        parser.error("--duration должен быть > 0")
    return args


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    frames = source_frames(args.src)
    if not frames:
        print(f"Нет кадров frame_*.png в {args.src}", file=sys.stderr)
        return 1

    first = QImage(str(frames[0]))
    if first.isNull():
        print(f"Не удалось прочитать кадр: {frames[0]}", file=sys.stderr)
        return 1
    target_w = max(1, round(first.width() * args.scale))
    target_h = max(1, round(first.height() * args.scale))

    scaled: list[QImage] = []
    for path in frames:
        image = QImage(str(path))
        if image.isNull():
            print(f"Не удалось прочитать кадр: {path}", file=sys.stderr)
            return 1
        if (image.width(), image.height()) != (first.width(), first.height()):
            print(f"Размер кадра отличается: {path}", file=sys.stderr)
            return 1
        scaled.append(
            image.convertToFormat(QImage.Format_RGBA8888).scaled(
                target_w,
                target_h,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
        )

    union: QRect | None = None
    for index, image in enumerate(scaled):
        bbox = frame_bbox(image)
        if bbox is None:
            print(
                f"Пустой кадр (нет пикселей с alpha≥{ALPHA_THRESHOLD}): {frames[index]}",
                file=sys.stderr,
            )
            return 1
        union = bbox if union is None else union.united(bbox)
    assert union is not None
    crop = union.adjusted(-PAD_PX, -PAD_PX, PAD_PX, PAD_PX).intersected(
        QRect(0, 0, target_w, target_h)
    )

    args.dst.mkdir(parents=True, exist_ok=True)
    for stale in args.dst.glob("_*.png"):
        stale.unlink()
    for index, image in enumerate(scaled):
        out_path = args.dst / f"_{index:03d}_{args.duration}.png"
        if not image.copy(crop).save(str(out_path), "PNG"):
            print(f"Не удалось сохранить: {out_path}", file=sys.stderr)
            return 1

    print(
        f"Клип сохранён: {args.dst} — {len(scaled)} кадров {crop.width()}×{crop.height()}, "
        f"{args.duration} мс/кадр, холст {target_w}×{target_h}, crop {crop.x()},{crop.y()}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
