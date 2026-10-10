"""Тесты слайсера шитов (scripts/slice_sheets.py) на синтетических шитах.

Ядро — масочная нарезка: в кадр попадают ТОЛЬКО пиксели его компонентов,
чужие пиксели внутри bbox исключаются; привязка кадра к слоту сетки
стабильна (не зависит от bbox); loop — по исходным ячейкам шита.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import scripts.slice_sheets as slice_sheets
from PySide6.QtGui import QColor, QImage, QPainter

CELL_W, CELL_H = 10, 20
RED = QColor(255, 0, 0, 255)
BLUE = QColor(0, 0, 255, 255)


def _count_color(png: QImage, color: QColor) -> int:
    """Сколько пикселей заданного цвета в PNG (проверка чужих пикселей)."""
    img = png.convertToFormat(QImage.Format.Format_RGBA8888)
    data = bytes(img.constBits())
    stride = img.bytesPerLine()
    total = 0
    for y in range(img.height()):
        for x in range(img.width()):
            if QColor(data[y * stride + x * 4], data[y * stride + x * 4 + 1],
                      data[y * stride + x * 4 + 2], data[y * stride + x * 4 + 3]) == color:
                total += 1
    return total


def _write_sheet(
    root: Path, *, cols: int, rows: int = 1, frames: set[tuple[int, int]] | None = None
) -> None:
    """Лист сетки cols×rows ячеек CELL_W×CELL_H; frames — ячейки со спрайтами.

    Спрайт — прямоугольник (CELL_W-2)×(CELL_H-2) с отступом 1 px внутри
    ячейки (между спрайтами — пустые промежутки 2 px). По умолчанию — все.
    """
    sheet_dir = root / "TEST SHEET"
    sheet_dir.mkdir(parents=True, exist_ok=True)
    img = QImage(CELL_W * cols, CELL_H * rows, QImage.Format.Format_RGBA8888)
    img.fill(QColor(0, 0, 0, 0))
    painter = QPainter(img)
    cells = frames if frames is not None else {(c, r) for r in range(rows) for c in range(cols)}
    for col, row in cells:
        painter.fillRect(
            col * CELL_W + 1, row * CELL_H + 1, CELL_W - 2, CELL_H - 2, RED
        )
    painter.end()
    assert img.save(str(sheet_dir / "sheet.png"), "PNG")


def _make_sheet(root: Path, w: int, h: int, draw: object) -> Path:
    """Лист w×h с произвольным содержимым (draw: painter -> None)."""
    sheet_dir = root / "TEST SHEET"
    sheet_dir.mkdir(parents=True, exist_ok=True)
    img = QImage(w, h, QImage.Format.Format_RGBA8888)
    img.fill(QColor(0, 0, 0, 0))
    painter = QPainter(img)
    draw(painter)  # type: ignore[operator]
    painter.end()
    path = sheet_dir / "sheet.png"
    assert img.save(str(path), "PNG")
    return path


def _plan(**kwargs: object) -> slice_sheets.ClipPlan:
    params: dict[str, object] = {
        "sheet": "TEST SHEET",
        "anim": "Test",
        "state": "Clip",
        "duration_ms": 100,
    }
    params.update(kwargs)
    return slice_sheets.ClipPlan(**params)  # type: ignore[arg-type]


@pytest.fixture
def sheet_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """OUT_ROOT во временном каталоге (не трогаем assets/)."""
    monkeypatch.setattr(slice_sheets, "OUT_ROOT", tmp_path / "out")
    return tmp_path


def _frame_path(root: Path, source_index: int) -> Path:
    return root / "out" / "Test" / "Clip" / "1" / f"_{source_index:03d}_100.png"


class TestMaskExtraction:
    """Масочная нарезка: чужие пиксели не попадают в кадр, свои не режутся."""

    def test_foreign_pixels_inside_bbox_excluded(self, sheet_root: Path) -> None:
        """Чужой компонент внутри bbox кадра не копируется (вместо кропа по bbox)."""

        def draw(painter: QPainter) -> None:
            # спрайт A: красный прямоугольник с «рвом» вокруг синего острова B
            painter.fillRect(2, 2, 19, 9, RED)  # x2..20 y2..10
            painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_Clear)
            painter.fillRect(14, 3, 6, 7, QColor(0, 0, 0, 0))  # прозрачный ров x14..19
            painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceOver)
            painter.fillRect(16, 4, 3, 5, BLUE)  # остров B внутри bbox A

        _make_sheet(sheet_root, 24, 12, draw)
        result = slice_sheets.slice_sheet(
            _plan(mode=slice_sheets.MODE_MANUAL, col_bounds=(0, 16, 24), expect=2),
            sheet_root,
        )

        assert result.errors == []
        assert result.frames_written == 2
        frame0 = QImage(str(_frame_path(sheet_root, 0)))
        frame1 = QImage(str(_frame_path(sheet_root, 1)))
        # ни одного чужого пикселя в чужом кадре
        assert _count_color(frame0, BLUE) == 0
        assert _count_color(frame1, RED) == 0
        # свои пиксели сохранены целиком (остров B — весь в кадре 1)
        assert _count_color(frame1, BLUE) == 3 * 5
        assert _count_color(frame0, RED) == 19 * 9 - 6 * 7  # A минус ров

    def test_crossover_component_written_whole(self, sheet_root: Path) -> None:
        """Кроссовер одного кадра (масса < порога в чужом слоте) не режется."""

        def draw(painter: QPainter) -> None:
            painter.fillRect(2, 2, 10, 7, RED)  # x2..11 y2..8, заходит за границу 10

        _make_sheet(sheet_root, 24, 12, draw)
        result = slice_sheets.slice_sheet(
            _plan(mode=slice_sheets.MODE_MANUAL, col_bounds=(0, 10, 24), expect=2),
            sheet_root,
        )

        assert result.errors == []
        frame0 = QImage(str(_frame_path(sheet_root, 0)))
        assert _count_color(frame0, RED) == 10 * 7  # весь компонент, без обреза

    def test_merged_component_split_with_warning(self, sheet_root: Path) -> None:
        """«Слитый» компонент в MANUAL режется по границе с предупреждением."""

        def draw(painter: QPainter) -> None:
            painter.fillRect(5, 2, 11, 7, RED)  # x5..15 пересекает границу 10

        _make_sheet(sheet_root, 24, 12, draw)
        result = slice_sheets.slice_sheet(
            _plan(mode=slice_sheets.MODE_MANUAL, col_bounds=(0, 10, 24), expect=2),
            sheet_root,
        )

        assert result.errors == []
        assert result.frames_written == 2
        assert any("разрезан" in warning for warning in result.warnings)
        assert _count_color(QImage(str(_frame_path(sheet_root, 0))), RED) == 5 * 7
        assert _count_color(QImage(str(_frame_path(sheet_root, 1))), RED) == 6 * 7

    def test_fringe_preserved_byte_exact(self, sheet_root: Path) -> None:
        """Полупрозрачная кайма сохраняется 1:1 и принадлежит кадру спрайта."""
        soft = QColor(255, 0, 0, 8)  # alpha < ALPHA_STRUCT

        def draw(painter: QPainter) -> None:
            painter.fillRect(2, 2, 8, 7, RED)
            painter.fillRect(10, 2, 1, 7, soft)  # кайма вплотную к спрайту

        _make_sheet(sheet_root, 20, 12, draw)
        result = slice_sheets.slice_sheet(_plan(), sheet_root)

        assert result.errors == []
        png = QImage(str(_frame_path(sheet_root, 0)))
        assert _count_color(png, soft) == 7  # вся кайма при своем спрайте (alpha 8 сохранён)
        assert _count_color(png, RED) == 8 * 7  # структура без потерь

    def test_auto_merged_component_is_error(self, sheet_root: Path) -> None:
        """AUTO: пиксельно слитые кадры — ошибка диагностики, а не порча кадров."""

        def draw(painter: QPainter) -> None:
            for x in (2, 14, 26):
                painter.fillRect(x, 2, 8, 18, RED)  # три обычных спрайта
            painter.fillRect(40, 2, 20, 18, RED)  # слитая пара (шире и тяжелее)

        _make_sheet(sheet_root, 64, 24, draw)
        result = slice_sheets.slice_sheet(_plan(expect=4), sheet_root)

        assert result.frames_written == 0
        assert any("слитых кадров" in error for error in result.errors)
        assert any("col_bounds" in error for error in result.errors)


class TestStableAnchor:
    """Стабильная привязка: кадр кладётся относительно слота, а не bbox."""

    def test_frames_keep_sheet_offsets(self, sheet_root: Path) -> None:
        """Одна и та же деталь в двух кадрах лежит на одном месте канвы."""

        def draw(painter: QPainter) -> None:
            painter.fillRect(2, 2, 8, 12, RED)  # спрайт 1: метка x3
            painter.fillRect(3, 5, 1, 1, BLUE)
            painter.fillRect(12, 4, 8, 12, RED)  # спрайт 2 сдвинут вниз, метка x13
            painter.fillRect(13, 7, 1, 1, BLUE)

        _make_sheet(sheet_root, 24, 20, draw)
        result = slice_sheets.slice_sheet(_plan(), sheet_root)

        assert result.errors == []
        marks = []
        for source_index in (0, 1):
            png = QImage(str(_frame_path(sheet_root, source_index)))
            img = png.convertToFormat(QImage.Format.Format_RGBA8888)
            data = bytes(img.constBits())
            stride = img.bytesPerLine()
            frame_marks = [
                (x, y)
                for y in range(img.height())
                for x in range(img.width())
                if data[y * stride + x * 4 + 2] == 255 and data[y * stride + x * 4 + 3] == 255
            ]
            assert len(frame_marks) == 1
            marks.append(frame_marks[0])
        # метка в слоте кадра 0 (x3) и слота кадра 1 (x13) — одинаковый dst_x
        assert marks[0][0] == marks[1][0]

    def test_rows_bottom_aligned_on_canvas(self, sheet_root: Path) -> None:
        """Ряды разной высоты выровнены по низу канвы (пол клипа общий)."""

        def draw(painter: QPainter) -> None:
            painter.fillRect(2, 2, 8, 20, RED)  # ряд 0: высота 20
            painter.fillRect(12, 30, 8, 8, RED)  # ряд 1: высота 8

        _make_sheet(sheet_root, 24, 42, draw)
        result = slice_sheets.slice_sheet(_plan(), sheet_root)

        assert result.errors == []
        tall = QImage(str(_frame_path(sheet_root, 0)))
        short = QImage(str(_frame_path(sheet_root, 1)))
        assert tall.height() == short.height() == 20  # канва одинаковая, 1:1 без масштаба
        # низ обоих кадров совпадает: ряд 1 прижат к низу канвы
        for png in (tall, short):
            img = png.convertToFormat(QImage.Format.Format_RGBA8888)
            data = bytes(img.constBits())
            stride = img.bytesPerLine()
            ys = [
                y
                for y in range(img.height())
                for x in range(img.width())
                if data[y * stride + x * 4 + 3] == 255
            ]
            assert max(ys) == png.height() - 1


class TestModes:
    """Режимы нарезки: AUTO (промежутки), GRID (сетка), MANUAL (границы)."""

    def test_grid_mode_uses_grid_slots(self, sheet_root: Path) -> None:
        """GRID: слоты равномерные, ячейки нумеруются по сетке."""
        _write_sheet(sheet_root, cols=3, rows=1)
        result = slice_sheets.slice_sheet(
            _plan(mode=slice_sheets.MODE_GRID, grid=(1, 3), expect=3), sheet_root
        )

        assert result.errors == []
        assert result.frames_written == 3
        assert result.sheet_cells == [0, 1, 2]
        assert result.mode == slice_sheets.MODE_GRID

    def test_manual_bounds_wrong_rows_is_error(self, sheet_root: Path) -> None:
        """MANUAL: границы обязаны описывать все ряды шита."""
        _write_sheet(sheet_root, cols=2, rows=2)
        result = slice_sheets.slice_sheet(
            _plan(
                mode=slice_sheets.MODE_MANUAL,
                col_bounds=((0, 10, 20),),  # один ряд при двух рядах шита
                expect=4,
            ),
            sheet_root,
        )

        assert result.frames_written == 0
        assert any("col_bounds" in error for error in result.errors)

    def test_manual_requires_bounds(self, sheet_root: Path) -> None:
        _write_sheet(sheet_root, cols=2, rows=1)
        result = slice_sheets.slice_sheet(
            _plan(mode=slice_sheets.MODE_MANUAL), sheet_root
        )
        assert any("требует col_bounds" in error for error in result.errors)


class TestValidation:
    """Валидация: expect, пропуски ячеек, индексы loop, аномалии."""

    def test_expect_mismatch_is_error(self, sheet_root: Path) -> None:
        _write_sheet(sheet_root, cols=2, rows=1)
        result = slice_sheets.slice_sheet(_plan(expect=3), sheet_root)
        assert result.frames_written == 0
        assert any("ожидалось 3" in error for error in result.errors)

    def test_missing_cell_keeps_source_indices(self, sheet_root: Path) -> None:
        """Пустая ячейка: нумерация не сжимается, пропуск в манифесте."""
        _write_sheet(sheet_root, cols=3, rows=2, frames={(0, 0), (1, 0), (2, 0), (0, 1), (2, 1)})
        result = slice_sheets.slice_sheet(_plan(expect=6), sheet_root)

        assert result.errors == []
        assert result.frames_written == 5
        assert result.missing_cells == [4]  # (row=1, col=1) → исходная ячейка 4
        out = sheet_root / "out" / "Test" / "Clip" / "1"
        names = sorted(p.name for p in out.glob("*.png"))
        assert "_004_100.png" not in names
        assert "_005_100.png" in names  # индексы исходных ячеек сохранены
        assert result.sheet_cells == [0, 1, 2, 3, 5]

    def test_loop_maps_source_indices_to_positions(self, sheet_root: Path) -> None:
        """loop плана — исходные ячейки; манифест получает позиции кадров."""
        _write_sheet(sheet_root, cols=3, rows=2, frames={(0, 0), (1, 0), (2, 0), (0, 1), (2, 1)})
        result = slice_sheets.slice_sheet(_plan(expect=6, loop=(3, 5)), sheet_root)

        assert result.errors == []
        # исходные ячейки 3..5 записаны как позиции 3..4 (ячейка 4 пуста)
        assert result.loop_positions == (3, 4)
        manifest = slice_sheets.format_manifest([result])
        assert "loop = [3, 4]" in manifest
        assert "missing_cells = [4]" in manifest

    def test_loop_with_missing_cell_warns(self, sheet_root: Path) -> None:
        _write_sheet(sheet_root, cols=3, rows=2, frames={(0, 0), (1, 0), (2, 0), (0, 1), (2, 1)})
        result = slice_sheets.slice_sheet(_plan(expect=6, loop=(4, 5)), sheet_root)

        assert result.errors == []
        assert any("пусты" in warning for warning in result.warnings)
        assert result.loop_positions == (4, 4)  # только записанная ячейка 5

    def test_slot_deviation_warns(self, sheet_root: Path) -> None:
        """Спутник далеко от слота кадра — предупреждение о чужом фрагменте."""

        def draw(painter: QPainter) -> None:
            painter.fillRect(2, 2, 8, 12, RED)
            painter.fillRect(12, 2, 8, 12, RED)
            painter.fillRect(5, 16, 2, 1, RED)  # мусор под кадром 0 — близко, без предупреждения

        _make_sheet(sheet_root, 24, 20, draw)
        result = slice_sheets.slice_sheet(_plan(), sheet_root)
        assert result.errors == []
        assert not any("отклоняется от слота" in warning for warning in result.warnings)


class TestAutoScaleFor:
    def test_stop_list_keeps_scale_one(self) -> None:
        """Сидячие позы не растут (стоп-лист)."""
        assert slice_sheets.auto_scale_for("Sit/Typing", 300) == 1.0
        assert slice_sheets.auto_scale_for("Hide/Out", 300) == 1.0

    def test_no_content_scale_one(self) -> None:
        assert slice_sheets.auto_scale_for("Walk/Right", 0) == 1.0

    def test_reference_height_scale(self) -> None:
        assert slice_sheets.auto_scale_for("Walk/Right", 229) == pytest.approx(2.0)

    def test_median_content_height(self, sheet_root: Path) -> None:
        """content_h — медиана; эффект-кадр не перетягивает масштаб клипа."""

        def draw(painter: QPainter) -> None:
            for x in (2, 14, 26):
                painter.fillRect(x, 12, 8, 8, RED)  # кадры высотой 8
            painter.fillRect(38, 2, 8, 18, RED)  # «прыжок» высотой 18

        _make_sheet(sheet_root, 50, 22, draw)
        result = slice_sheets.slice_sheet(_plan(), sheet_root)

        assert result.content_h == 8  # медиана, а не максимум (18)
        assert result.scale == pytest.approx(slice_sheets.REF_HEIGHT_PX / 8)  # главная поза 8

    def test_main_pose_height_morphing_keeps_stance(self) -> None:
        """Морфинг (мяч, калачик) не перетягивает масштаб: главная поза — стойка."""
        # Sleep/Wake: калачик 290–335 не должен растить стойку (429) выше эталона
        assert slice_sheets.main_pose_height([429, 426, 335, 290, 306, 302, 365]) == 429

    def test_main_pose_height_skips_effect_frames(self) -> None:
        """Эффект-кадр выше MAIN_POSE_RATIO × медианы в главную позу не входит."""
        assert slice_sheets.main_pose_height([8, 8, 8, 18]) == 8

    def test_main_pose_height_empty(self) -> None:
        assert slice_sheets.main_pose_height([]) == 0


class TestDiagnostics:
    def test_diagnostics_png_written(self, sheet_root: Path) -> None:
        _write_sheet(sheet_root, cols=2, rows=1)
        result = slice_sheets.slice_sheet(_plan(), sheet_root)
        assert result.errors == []
        diag = sheet_root / "out" / "_diagnostics" / "TEST SHEET.png"
        assert diag.is_file()
        assert not QImage(str(diag)).isNull()

    def test_diagnostics_written_on_error(self, sheet_root: Path) -> None:
        """Ошибки алгоритма видны до экспорта — диагностика пишется и при ошибке."""
        _write_sheet(sheet_root, cols=2, rows=1)
        result = slice_sheets.slice_sheet(_plan(expect=5), sheet_root)
        assert result.errors
        assert (sheet_root / "out" / "_diagnostics" / "TEST SHEET.png").is_file()


class TestResolveSheetDir:
    def test_normalized_spaces_match(self, tmp_path: Path) -> None:
        """Каталог с двойными пробелами находится по нормализованному имени."""
        (tmp_path / "TEST  SHEET ").mkdir()
        found = slice_sheets.resolve_sheet_dir(tmp_path, "TEST SHEET")
        assert found is not None
        assert found.name == "TEST  SHEET "

    def test_missing_dir_returns_none(self, tmp_path: Path) -> None:
        assert slice_sheets.resolve_sheet_dir(tmp_path, "NOPE") is None
