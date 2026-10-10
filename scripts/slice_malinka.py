"""Нарезка шита девочки-малинки → assets/characters/malinka/ (PHASE 4, ассеты).

Границы рядов/колонок — реальные пустые зоны шита (профили alpha, НЕ номинальные
184/189.6 — ряды имеют разную высоту 141..192). Каждый кадр кладётся на единый
холст 191x192: якорь «низ» (общий пол, ноги на одном уровне) + центр по X.

Использование:
    .venv/bin/python scripts/slice_malinka.py [ПУТЬ_К_ШИТУ]
Шит по умолчанию — assets/Милый спрайт-лист девочки-малинки.png; после переработки
исходника задайте новый файл первым аргументом (границы рядов/колонок — свои).
"""
import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from pathlib import Path

from PySide6.QtGui import QColor, QGuiApplication, QImage, QPainter

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SRC = ROOT / "assets" / "Милый спрайт-лист девочки-малинки.png"
SRC = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_SRC
OUT_ROOT = ROOT / "assets" / "characters" / "malinka"

# реальные границы рядов [y0, y1) по пустым зонам шита
ROW_BOUNDS = [
    (10, 202),
    (208, 391),
    (398, 580),
    (594, 752),
    (757, 941),
    (948, 1127),
    (1133, 1318),
    (1320, 1496),
    (1500, 1641),
]
# реальные границы колонок [x0, x1); колонка 4/5 — по номиналу (пустоты нет)
COL_BOUNDS = [(29, 213), (213, 387), (387, 568), (568, 759), (759, 940)]

# Граница 4/5-й колонки для рядов, где контент 5-й колонки заходит за номинал 759
# и разрезается посередине: у Happy туда попадают «искры» выражения (x739..765),
# у Thinking — хвост дыма и словарь волос (x727..758). Сдвиг — в реальные долины
# профиля alpha между колонками (Happy: 714..723, Thinking: 727..730).
COL_BOUNDS_BY_ROW: dict[int, list[tuple[int, int]]] = {
    1: [(29, 213), (213, 387), (387, 568), (568, 720), (720, 940)],   # Happy
    6: [(29, 213), (213, 387), (387, 568), (568, 728), (728, 940)],   # Thinking
}

# ряд (0-based) → (Анимация, Состояние, длительность_мс); один ряд = один клип
PLAN: dict[int, tuple[str, str, int]] = {
    0: ("Idle", "Normal", 150),      # стоит
    1: ("Happy", "Normal", 120),     # радуется
    2: ("Walk", "Normal", 120),      # идёт влево (зеркало — рантайм, PHASE 4)
    3: ("Run", "Normal", 90),        # быстрый бег влево (зеркало — рантайм)
    4: ("Coffee", "Normal", 200),    # пьёт кофе
    5: ("Sit", "Working", 250),      # воркинг с ноутбуком
    6: ("Thinking", "Normal", 200),  # курит (обычное действие)
    7: ("Sleep", "Stand", 300),      # засыпает стоя
    8: ("Sleep", "Lay", 300),        # засыпает лёжа
}

CANVAS_W, CANVAS_H = 191, 192  # единый холст всех кадров


def alpha_bbox(cell: QImage) -> tuple[int, int, int, int] | None:
    """bbox контента с alpha>=64; None — ячейка пустая."""
    data = bytes(cell.constBits())
    stride = cell.bytesPerLine()
    x0, y0, x1, y1 = cell.width(), cell.height(), -1, -1
    for y in range(cell.height()):
        row = y * stride
        for x in range(cell.width()):
            if data[row + x * 4 + 3] >= 64:
                x0 = min(x0, x)
                x1 = max(x1, x)
                y0 = min(y0, y)
                y1 = max(y1, y)
    if x1 < 0:
        return None
    return x0, y0, x1, y1


def main() -> int:
    app = QGuiApplication.instance() or QGuiApplication([])
    del app
    img = QImage(str(SRC))
    if img.isNull():
        print(f"ОШИБКА: не удалось открыть {SRC}", file=sys.stderr)
        return 1
    img = img.convertToFormat(QImage.Format.Format_RGBA8888)
    print(f"Шит: {img.width()}x{img.height()}")

    problems: list[str] = []
    written = 0
    for row, (anim, state, duration_ms) in PLAN.items():
        y0, y1 = ROW_BOUNDS[row]
        row_h = y1 - y0
        line_dir = OUT_ROOT / anim / state / "1"
        line_dir.mkdir(parents=True, exist_ok=True)
        col_bounds = COL_BOUNDS_BY_ROW.get(row, COL_BOUNDS)
        for col, (x0, x1) in enumerate(col_bounds):
            cell = img.copy(x0, y0, x1 - x0, row_h)
            bbox = alpha_bbox(cell)
            tag = f"{anim}/{state} кадр {col}"
            if bbox is None:
                problems.append(f"ПУСТАЯ ячейка: {tag} (x{x0}..{x1} y{y0}..{y1})")
                continue
            # единый холст: низ = пол, центр по X
            canvas = QImage(CANVAS_W, CANVAS_H, QImage.Format.Format_RGBA8888)
            canvas.fill(QColor(0, 0, 0, 0))
            painter = QPainter(canvas)
            painter.drawImage((CANVAS_W - cell.width()) // 2, CANVAS_H - cell.height(), cell)
            painter.end()
            path = line_dir / f"_{col:03d}_{duration_ms}.png"
            if not canvas.save(str(path)):
                problems.append(f"не сохранился: {path}")
                continue
            written += 1
            print(
                f"  {path.relative_to(ROOT)}  ячейка {cell.width()}x{cell.height()} bbox={bbox}"
            )

    print(f"\nСохранено кадров: {written}")
    if problems:
        print(f"\nПРОБЛЕМЫ ({len(problems)}):")
        for problem in problems:
            print(f"  - {problem}")
    return 0 if written == len(PLAN) * len(COL_BOUNDS) else 1


if __name__ == "__main__":
    raise SystemExit(main())