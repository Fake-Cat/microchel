"""Загрузка кадров анимации в формате VPet: _NNN_DDD.png (ADR-005, FR-P2.1, FR-P2.2).

Чистая логика без Qt — тестируется юнит-тестами.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)

FRAME_NAME_RE = re.compile(r"^_(?P<index>\d+)_(?P<duration>\d+)\.png$")


def parse_frame_name(name: str) -> tuple[int, int] | None:
    """Разобрать имя кадра `_NNN_DDD.png` → (номер, длительность_мс) или None."""
    match = FRAME_NAME_RE.match(name)
    if match is None:
        return None
    index = int(match.group("index"))
    duration_ms = int(match.group("duration"))
    if duration_ms <= 0:
        return None
    return index, duration_ms


@dataclass(frozen=True, slots=True)
class FrameSpec:
    """Один кадр: номер, длительность показа (из имени файла) и путь."""

    index: int
    duration_ms: int
    path: Path


@dataclass(frozen=True, slots=True)
class AnimationClip:
    """Упорядоченная последовательность кадров одного клипа (каталог линии)."""

    name: str
    line: int
    frames: tuple[FrameSpec, ...]

    @property
    def total_duration_ms(self) -> int:
        return sum(frame.duration_ms for frame in self.frames)


class ClipLoadError(ValueError):
    """Каталог не содержит валидных кадров анимации."""


def _parse_line(clip_dir: Path) -> int:
    """Линия анимации — имя родительского каталога (1/2/3), иначе 1."""
    if clip_dir.name.isdigit():
        line = int(clip_dir.name)
        if 1 <= line <= 99:
            return line
    return 1


def load_clip(clip_dir: Path, *, name: str | None = None) -> AnimationClip:
    """Загрузить клип из каталога кадров.

    Имя клипа по умолчанию — `<Анимация>/<Состояние>` (два уровня над линией).
    Чужие PNG пропускаются с предупреждением (FR-P2.1); пустой каталог — ошибка.
    """
    if not clip_dir.is_dir():
        raise ClipLoadError(f"нет каталога кадров: {clip_dir}")
    frames: list[FrameSpec] = []
    for path in sorted(clip_dir.iterdir()):
        if not path.is_file():
            continue
        parsed = parse_frame_name(path.name)
        if parsed is None:
            if path.suffix.lower() == ".png":
                logger.warning("Пропущен PNG с не-форматным именем: %s", path)
            continue
        index, duration_ms = parsed
        frames.append(FrameSpec(index=index, duration_ms=duration_ms, path=path))
    if not frames:
        raise ClipLoadError(f"нет кадров формата _NNN_DDD.png: {clip_dir}")
    frames.sort(key=lambda frame: frame.index)
    if name is None:
        # типовая иерархия: <Анимация>/<Состояние>/<Линия>/ → имя «Анимация/Состояние»
        if clip_dir.name.isdigit():
            clip_name = f"{clip_dir.parent.parent.name}/{clip_dir.parent.name}"
        else:
            clip_name = f"{clip_dir.parent.name}/{clip_dir.name}"
    else:
        clip_name = name
    return AnimationClip(name=clip_name, line=_parse_line(clip_dir), frames=tuple(frames))


def discover_clip_dirs(root: Path) -> list[Path]:
    """Найти каталоги кадров: root/<Анимация>/<Состояние>/<Линия>/."""
    if not root.is_dir():
        return []
    result: list[Path] = []
    for line_dir in sorted(root.glob("*/*/*")):
        if not line_dir.is_dir():
            continue
        has_frames = any(
            parse_frame_name(path.name) is not None
            for path in line_dir.iterdir()
            if path.is_file()
        )
        if has_frames:
            result.append(line_dir)
    return result
