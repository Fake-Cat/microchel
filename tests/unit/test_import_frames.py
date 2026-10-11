"""Тесты импортёра кадров (scripts/import_frames.py) на синтетических лентах.

Сегментация — по содержимому: профиль плотности столбцов, деление
слипшихся поз по «горлышкам», аварийный разрез по медиане ширины; сетка
и размер ячеек не предполагаются. Материал собственный, временный.
"""

from __future__ import annotations

import logging
import tomllib
from pathlib import Path

import pytest
import scripts.import_frames as import_frames
from PySide6.QtGui import QColor, QImage, QPainter

RED = QColor(255, 0, 0, 255)


def _write_strip(
    path: Path,
    width: int,
    height: int,
    rects: list[tuple[int, int, int, int]],
    *,
    noise_cols: tuple[int, ...] = (),
) -> None:
    """Лента: непрозрачные прямоугольники (x0, x1, y0, y1, включительно) + шум."""
    img = QImage(width, height, QImage.Format.Format_RGBA8888)
    img.fill(QColor(0, 0, 0, 0))
    painter = QPainter(img)
    for x0, x1, y0, y1 in rects:
        painter.fillRect(x0, y0, x1 - x0 + 1, y1 - y0 + 1, RED)
    for x in noise_cols:
        painter.fillRect(x, 0, 1, 1, RED)  # плотность столбца = 1 — ниже порога
    painter.end()
    path.parent.mkdir(parents=True, exist_ok=True)
    assert img.save(str(path), "PNG")


def _import(tmp_path: Path, *extra: str) -> tuple[int, Path]:
    """Запуск импортёра во временный каталог; (код возврата, каталог кадров)."""
    frames_root = tmp_path / "frames"
    argv = [
        "--src",
        str(tmp_path / "src"),
        "--clip",
        "Test/Clip",
        "--frames-root",
        str(frames_root),
        *extra,
    ]
    rc = import_frames.run(import_frames.parse_args(argv))
    return rc, frames_root / "Test" / "Clip" / "1"


def _widths(dst: Path) -> list[int]:
    """Ширины записанных кадров в порядке имён (_NNN_DDD.png)."""
    return [QImage(str(path)).width() for path in sorted(dst.glob("_*.png"))]


class TestSegmentation:
    """Разрез ленты по содержимому: зазоры, шум, слипшиеся позы, аномалии."""

    def test_gap_split_two_poses(self, tmp_path: Path) -> None:
        """Две позы с зазором — два кадра по ширинам поз."""
        _write_strip(tmp_path / "src" / "1.png", 280, 100, [(20, 119, 10, 89), (160, 259, 10, 89)])
        rc, dst = _import(tmp_path, "--duration", "16")
        assert rc == 0
        assert _widths(dst) == [100, 100]

    def test_noise_and_narrow_runs_dropped(
        self, tmp_path: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Шумовые столбцы и узкие прогоны отбрасываются с предупреждением."""
        _write_strip(
            tmp_path / "src" / "1.png",
            340,
            100,
            [(20, 119, 10, 89), (160, 259, 10, 89), (300, 314, 10, 89)],
            noise_cols=tuple(range(125, 156)),
        )
        caplog.set_level(logging.WARNING, logger="import_frames")
        rc, dst = _import(tmp_path, "--duration", "16")
        assert rc == 0
        assert _widths(dst) == [100, 100]
        assert any("шум" in message for message in caplog.messages)

    def test_stuck_poses_split_by_neck(self, tmp_path: Path) -> None:
        """Слипшиеся позы с тонким горлышком разрезаются по минимуму профиля."""
        # позы 100px с высотой 80, горлышко 30px с высотой 10 посередине
        _write_strip(
            tmp_path / "src" / "1.png",
            280,
            100,
            [(20, 119, 10, 89), (120, 149, 80, 89), (150, 249, 10, 89)],
        )
        rc, dst = _import(tmp_path, "--duration", "16")
        assert rc == 0
        widths = sorted(_widths(dst))
        assert len(widths) == 2
        assert sum(widths) == 229  # столбец разреза отброшен
        assert all(w >= 100 for w in widths)

    def test_emergency_split_wide_block(
        self, tmp_path: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Блок из слипшихся поз без горлышка режется по медиане ширин соседей."""
        _write_strip(
            tmp_path / "src" / "1.png",
            720,
            100,
            [
                (20, 119, 10, 89),
                (150, 249, 10, 89),
                (280, 379, 10, 89),
                (400, 699, 10, 89),  # три позы вплотную, без зазоров и горлышек
            ],
        )
        caplog.set_level(logging.WARNING, logger="import_frames")
        rc, dst = _import(tmp_path, "--duration", "16")
        assert rc == 0
        assert _widths(dst) == [100, 100, 100, 100, 100, 100]
        assert any("аварийный разрез" in message for message in caplog.messages)

    def test_single_wide_frame_not_split(self, tmp_path: Path) -> None:
        """Один кадр на файл: сравнивать не с чем, широкая поза не режется."""
        _write_strip(tmp_path / "src" / "1.png", 340, 100, [(20, 319, 10, 89)])
        rc, dst = _import(tmp_path, "--duration", "16")
        assert rc == 0
        assert _widths(dst) == [300]

    def test_numeric_file_order(self, tmp_path: Path) -> None:
        """Файлы сортируются по числу: 1.png, 2.png, 10.png — не лексикографически."""
        for name, x1 in (("1.png", 119), ("2.png", 139), ("10.png", 159)):
            _write_strip(tmp_path / "src" / name, 200, 100, [(20, x1, 10, 89)])
        rc, dst = _import(tmp_path, "--duration", "16")
        assert rc == 0
        assert _widths(dst) == [100, 120, 140]

    def test_scale_applied_offline(self, tmp_path: Path) -> None:
        """--scale уменьшает кадры офлайн (полная высота холста масштабируется)."""
        _write_strip(tmp_path / "src" / "1.png", 280, 100, [(20, 119, 10, 89)])
        rc, dst = _import(tmp_path, "--duration", "16", "--scale", "0.5")
        assert rc == 0
        frame = QImage(str(next(dst.glob("_*.png"))))
        assert (frame.width(), frame.height()) == (50, 50)


class TestNaming:
    """Имена кадров _NNN_DDD.png и длительности (ADR-005)."""

    def test_uniform_duration(self, tmp_path: Path) -> None:
        _write_strip(tmp_path / "src" / "1.png", 280, 100, [(20, 119, 10, 89), (160, 259, 10, 89)])
        rc, dst = _import(tmp_path, "--duration", "16")
        assert rc == 0
        assert sorted(p.name for p in dst.glob("_*.png")) == ["_000_016.png", "_001_016.png"]

    def test_durations_list(self, tmp_path: Path) -> None:
        _write_strip(tmp_path / "src" / "1.png", 280, 100, [(20, 119, 10, 89), (160, 259, 10, 89)])
        rc, dst = _import(tmp_path, "--durations", "16, 32")
        assert rc == 0
        assert sorted(p.name for p in dst.glob("_*.png")) == ["_000_016.png", "_001_032.png"]

    def test_durations_count_mismatch_is_error(self, tmp_path: Path) -> None:
        """Список длительностей ≠ числу кадров — ошибка, файлы не пишутся."""
        _write_strip(tmp_path / "src" / "1.png", 280, 100, [(20, 119, 10, 89), (160, 259, 10, 89)])
        rc, dst = _import(tmp_path, "--durations", "16")
        assert rc != 0
        assert not list(dst.glob("_*.png"))

class TestManifest:
    """Авто-обновление секции clips.toml: создание, сброс устаревших полей."""

    OLD = (
        "# clips.toml — тестовая шапка.\n"
        "\n"
        '[clips."Test/Clip"]\n'
        "frames = 12\n"
        "sheet_cells = [0, 1]\n"
        "missing_cells = [5]\n"
        "loop = [4, 10]\n"
        "repeat_fill_ms = 4000\n"
        "scale = 1.104\n"
        "\n"
        '[clips."Other/Clip"]\n'
        "frames = 3\n"
        "once = true\n"
    )

    @staticmethod
    def _write_manifest(tmp_path: Path, text: str) -> Path:
        manifest = tmp_path / "frames" / "clips.toml"
        manifest.parent.mkdir(parents=True, exist_ok=True)
        manifest.write_text(text, encoding="utf-8")
        return manifest

    @staticmethod
    def _section(manifest: Path, name: str) -> dict[str, object]:
        return tomllib.loads(manifest.read_text(encoding="utf-8"))["clips"][name]

    def test_new_manifest_created(self, tmp_path: Path) -> None:
        """Без clips.toml секция создаётся с числом кадров."""
        _write_strip(tmp_path / "src" / "1.png", 280, 100, [(20, 119, 10, 89), (160, 259, 10, 89)])
        rc, _ = _import(tmp_path, "--duration", "16")
        assert rc == 0
        section = self._section(tmp_path / "frames" / "clips.toml", "Test/Clip")
        assert section["frames"] == 2

    def test_stale_fields_dropped_playback_preserved(self, tmp_path: Path, caplog) -> None:
        """sheet_cells/loop/scale сброшены громко, repeat_fill_ms сохранён."""
        manifest = self._write_manifest(tmp_path, self.OLD)
        _write_strip(tmp_path / "src" / "1.png", 280, 100, [(20, 119, 10, 89), (160, 259, 10, 89)])
        caplog.set_level(logging.WARNING, logger="import_frames")
        rc, _ = _import(tmp_path, "--duration", "16")
        assert rc == 0
        section = self._section(manifest, "Test/Clip")
        assert section["frames"] == 2
        assert section["repeat_fill_ms"] == 4000
        for field in ("sheet_cells", "missing_cells", "loop", "scale"):
            assert field not in section
        other = self._section(manifest, "Other/Clip")
        assert other == {"frames": 3, "once": True}
        messages = "\n".join(caplog.messages)
        assert "sheet_cells" in messages and "loop" in messages and "scale" in messages

    def test_explicit_loop_written_once_dropped(self, tmp_path: Path, caplog) -> None:
        """--loop перекрывает спеку; конфликтующий once сбрасывается с предупреждением."""
        manifest = self._write_manifest(
            tmp_path, '[clips."Test/Clip"]\nframes = 12\nonce = true\n'
        )
        _write_strip(tmp_path / "src" / "1.png", 280, 100, [(20, 119, 10, 89), (160, 259, 10, 89)])
        caplog.set_level(logging.WARNING, logger="import_frames")
        rc, _ = _import(tmp_path, "--duration", "16", "--loop", "0:1")
        assert rc == 0
        section = self._section(manifest, "Test/Clip")
        assert section["loop"] == [0, 1]
        assert "once" not in section
        assert any("once" in message for message in caplog.messages)

    def test_expect_mismatch_is_error(self, tmp_path: Path) -> None:
        """--expect ≠ факту — ошибка до записи: кадры и манифест не тронуты."""
        _write_strip(tmp_path / "src" / "1.png", 280, 100, [(20, 119, 10, 89), (160, 259, 10, 89)])
        rc, dst = _import(tmp_path, "--duration", "16", "--expect", "60")
        assert rc != 0
        assert not list(dst.glob("_*.png"))
        assert not (tmp_path / "frames" / "clips.toml").exists()

    def test_loop_out_of_range_is_error(self, tmp_path: Path) -> None:
        """loop за пределами клипа — ошибка до записи."""
        _write_strip(tmp_path / "src" / "1.png", 280, 100, [(20, 119, 10, 89), (160, 259, 10, 89)])
        rc, dst = _import(tmp_path, "--duration", "16", "--loop", "0:5")
        assert rc != 0
        assert not list(dst.glob("_*.png"))


class TestPlaybackOffscreen:
    """Кадры читаются загрузчиком, спека — планом показа без обрезки (офскрейн)."""

    def test_load_clip_specs_and_plan(self, tmp_path: Path) -> None:
        from microchel.animation.frames import load_clip
        from microchel.animation.spec import load_clip_specs, plan_frames

        _write_strip(tmp_path / "src" / "1.png", 280, 100, [(20, 119, 10, 89), (160, 259, 10, 89)])
        rc, dst = _import(tmp_path, "--duration", "16")
        assert rc == 0

        clip = load_clip(dst, name="Test/Clip")
        assert [frame.duration_ms for frame in clip.frames] == [16, 16]

        spec = load_clip_specs(tmp_path / "frames" / "clips.toml")["Test/Clip"]
        assert spec.frames == 2
        assert spec.loop is None
        assert plan_frames(spec, [16, 16]).indices == (0, 1)