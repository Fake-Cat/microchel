"""Юнит-тесты парсинга и загрузки клипов (PHASE 2, FR-P2.1, FR-P2.2)."""

from __future__ import annotations

from pathlib import Path

import pytest

from microchel.animation.frames import (
    ClipLoadError,
    discover_clip_dirs,
    load_clip,
    parse_frame_name,
)


class TestParseFrameName:
    def test_valid_name(self) -> None:
        assert parse_frame_name("_000_250.png") == (0, 250)

    def test_multi_digit_duration(self) -> None:
        assert parse_frame_name("_012_1000.png") == (12, 1000)

    def test_missing_underscore_prefix(self) -> None:
        assert parse_frame_name("000_250.png") is None

    def test_wrong_extension(self) -> None:
        assert parse_frame_name("_000_250.jpg") is None

    def test_garbage_name(self) -> None:
        assert parse_frame_name("idle.png") is None

    def test_zero_duration_invalid(self) -> None:
        assert parse_frame_name("_000_0.png") is None

    def test_negative_duration_invalid(self) -> None:
        assert parse_frame_name("_000_-5.png") is None


def _make_frame_files(directory: Path, names: list[str]) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    for name in names:
        (directory / name).write_bytes(b"")


class TestLoadClip:
    def test_sorted_by_index(self, tmp_path: Path) -> None:
        _make_frame_files(tmp_path, ["_002_100.png", "_000_200.png", "_001_300.png"])
        clip = load_clip(tmp_path, name="Test/State")
        assert [frame.index for frame in clip.frames] == [0, 1, 2]
        assert [frame.duration_ms for frame in clip.frames] == [200, 300, 100]
        assert clip.total_duration_ms == 600

    def test_default_name_from_parents(self, tmp_path: Path) -> None:
        line_dir = tmp_path / "Idle" / "Happy" / "1"
        _make_frame_files(line_dir, ["_000_250.png"])
        clip = load_clip(line_dir)
        assert clip.name == "Idle/Happy"
        assert clip.line == 1

    def test_line_parsed_from_dir_name(self, tmp_path: Path) -> None:
        line_dir = tmp_path / "Idle" / "Happy" / "2"
        _make_frame_files(line_dir, ["_000_250.png"])
        assert load_clip(line_dir).line == 2

    def test_line_defaults_to_one(self, tmp_path: Path) -> None:
        _make_frame_files(tmp_path, ["_000_250.png"])
        assert load_clip(tmp_path).line == 1

    def test_foreign_png_skipped(self, tmp_path: Path) -> None:
        _make_frame_files(tmp_path, ["_000_250.png", "preview.png", "readme.txt"])
        clip = load_clip(tmp_path, name="T/S")
        assert len(clip.frames) == 1

    def test_empty_dir_raises(self, tmp_path: Path) -> None:
        tmp_path.mkdir(exist_ok=True)
        with pytest.raises(ClipLoadError):
            load_clip(tmp_path)

    def test_missing_dir_raises(self, tmp_path: Path) -> None:
        with pytest.raises(ClipLoadError):
            load_clip(tmp_path / "nope")

    def test_only_junk_raises(self, tmp_path: Path) -> None:
        _make_frame_files(tmp_path, ["preview.png"])
        with pytest.raises(ClipLoadError):
            load_clip(tmp_path)


class TestDiscoverClipDirs:
    def test_finds_line_dirs(self, tmp_path: Path) -> None:
        wanted = tmp_path / "Idle" / "Happy" / "1"
        _make_frame_files(wanted, ["_000_250.png"])
        _make_frame_files(tmp_path / "Blink" / "Happy" / "1", ["_000_60.png"])
        assert discover_clip_dirs(tmp_path) == [
            tmp_path / "Blink" / "Happy" / "1",
            tmp_path / "Idle" / "Happy" / "1",
        ]

    def test_missing_root(self, tmp_path: Path) -> None:
        assert discover_clip_dirs(tmp_path / "nope") == []

    def test_dir_without_frames_not_found(self, tmp_path: Path) -> None:
        (tmp_path / "A" / "S" / "1").mkdir(parents=True)
        assert discover_clip_dirs(tmp_path) == []

    def test_shallow_dirs_ignored(self, tmp_path: Path) -> None:
        _make_frame_files(tmp_path / "loose", ["_000_250.png"])
        assert discover_clip_dirs(tmp_path) == []
