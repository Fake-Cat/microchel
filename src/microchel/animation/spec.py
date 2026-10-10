"""Playback-спека клипов (PHASE 4): загрузка clips.toml и план показа.

Чистая логика без Qt — тестируется юнит-тестами. Спека описывает, КАК клип
играть (сегмент loop, повторы, зеркало, движение), а не что играть. Источник —
assets/characters/<персонаж>/clips.toml (генерируется scripts/slice_sheets.py).
План показа (`plan_frames`) повторяет рантайм-правила; `--showcase` играет
полный цикл каждой анимации (без слота), slot_ms — ограничение для будущих
сценариев показа (FSM-слоты).
"""

from __future__ import annotations

import logging
import random
import tomllib
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)

# допустимые значения полей спеки (лишнее — warning + дефолт)
MIRROR_VALUES = ("left",)
MOTION_VALUES = ("none", "walk", "traverse")


@dataclass(frozen=True, slots=True)
class ClipSpec:
    """Секция [clips."Имя"] из clips.toml (дефолты = без уточнений)."""

    name: str = ""
    frames: int = 0
    loop: tuple[int, int] | None = None  # повторяемый сегмент [a, b] включительно
    once: bool = False  # один проход и завершение
    prefix_once: bool = False  # кадры до loop — один раз перед циклом
    suffix_on_exit: bool = False  # после loop доиграть хвост при выходе
    repeat_fill_ms: int | None = None  # «несколько раз»: повторов ~ заполнить цель
    mirror: str | None = None  # "left" — показывать зеркально (спрайт идёт влево)
    motion: str = "none"  # walk / traverse / none — движение окна во время клипа
    scale: float = 1.0  # рантайм-масштаб (1.0 — без изменений)


@dataclass(frozen=True, slots=True)
class FramePlan:
    """Готовый план показа: индексы кадров клипа в порядке проигрывания."""

    indices: tuple[int, ...]
    mirror: bool = False


def _is_int(value: object) -> bool:
    """Целое, но не bool (bool — подкласс int в Python)."""
    return isinstance(value, int) and not isinstance(value, bool)


def load_clip_specs(path: Path) -> dict[str, ClipSpec]:
    """Прочитать playback-спеку из clips.toml.

    Отсутствие файла — не ошибка (клипы играют «как есть»); битый TOML —
    error-лог и пустая спека. Невалидные значения полей — warning + дефолт.
    """
    if not path.is_file():
        logger.info("Playback-спека не найдена: %s — клипы без уточнений", path)
        return {}
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as error:
        logger.error("Спека не читается %s: %s", path, error)
        return {}
    try:
        data = tomllib.loads(text)
    except tomllib.TOMLDecodeError as error:
        logger.error("Спека — битый TOML %s: %s", path, error)
        return {}
    raw_clips = data.get("clips")
    if not isinstance(raw_clips, dict):
        logger.warning("Спека без секций [clips.*]: %s", path)
        return {}
    specs: dict[str, ClipSpec] = {}
    for name, raw in raw_clips.items():
        if not isinstance(raw, dict):
            logger.warning("Секция [%s] не таблица — пропущена", name)
            continue
        specs[name] = _parse_spec(name, raw)
    logger.debug("Playback-спека: %s — %d клипов", path, len(specs))
    return specs


def _parse_spec(name: str, raw: dict[object, object]) -> ClipSpec:
    """Собрать ClipSpec из сырой секции; битые поля — warning + дефолт."""
    frames = raw.get("frames")
    if not _is_int(frames) or int(frames) <= 0:
        if frames is not None:
            logger.warning("Спека %r: frames=%r не положительное целое", name, frames)
        frames = 0

    loop: tuple[int, int] | None = None
    raw_loop = raw.get("loop")
    if raw_loop is not None:
        if (
            isinstance(raw_loop, (list, tuple))
            and len(raw_loop) == 2
            and all(_is_int(item) for item in raw_loop)
        ):
            start, end = int(raw_loop[0]), int(raw_loop[1])
            in_bounds = start >= 0 and start <= end and (not frames or end < frames)
            if in_bounds:
                loop = (start, end)
            else:
                logger.warning(
                    "Спека %r: loop=%r вне границ [0, %s) — игнорируется",
                    name,
                    list(raw_loop),
                    frames or "?",
                )
        else:
            logger.warning("Спека %r: loop=%r не пара целых — игнорируется", name, raw_loop)

    repeat_fill_ms: int | None = None
    raw_fill = raw.get("repeat_fill_ms")
    if raw_fill is not None:
        if _is_int(raw_fill) and raw_fill > 0:
            repeat_fill_ms = raw_fill
        else:
            logger.warning(
                "Спека %r: repeat_fill_ms=%r не положительное целое — игнорируется",
                name,
                raw_fill,
            )

    mirror: str | None = None
    raw_mirror = raw.get("mirror")
    if raw_mirror is not None:
        if raw_mirror in MIRROR_VALUES:
            mirror = str(raw_mirror)
        else:
            logger.warning(
                "Спека %r: mirror=%r не из %s — игнорируется", name, raw_mirror, MIRROR_VALUES
            )

    motion = "none"
    raw_motion = raw.get("motion")
    if raw_motion is not None:
        if raw_motion in MOTION_VALUES:
            motion = str(raw_motion)
        else:
            logger.warning(
                "Спека %r: motion=%r не из %s — принимается «none»",
                name,
                raw_motion,
                MOTION_VALUES,
            )

    scale = 1.0
    raw_scale = raw.get("scale")
    if raw_scale is not None:
        if (
            isinstance(raw_scale, (int, float))
            and not isinstance(raw_scale, bool)
            and raw_scale > 0
        ):
            scale = float(raw_scale)
        else:
            logger.warning(
                "Спека %r: scale=%r не положительное число — принимается 1.0", name, raw_scale
            )

    def _flag(field_name: str) -> bool:
        value = raw.get(field_name)
        if value is None:
            return False
        if not isinstance(value, bool):
            logger.warning("Спека %r: %s=%r не bool — принимается false", name, field_name, value)
            return False
        return value

    return ClipSpec(
        name=name,
        frames=frames,
        loop=loop,
        once=_flag("once"),
        prefix_once=_flag("prefix_once"),
        suffix_on_exit=_flag("suffix_on_exit"),
        repeat_fill_ms=repeat_fill_ms,
        mirror=mirror,
        motion=motion,
        scale=scale,
    )


def plan_frames(
    spec: ClipSpec,
    durations_ms: Sequence[int],
    *,
    slot_ms: int | None = None,
    rng: random.Random | None = None,
) -> FramePlan:
    """Последовательность кадров клипа для показа (правила спеки).

    - once — один проход всего клипа;
    - иначе loop-сегмент [a, b] (без loop — весь клип) повторяется:
      * repeat_fill_ms — случайное число повторов, ~ заполняющих цель;
      * slot_ms — loop крутится ровно до конца слота (ограничение для
        показов; repeat_fill_ms при наличии ограничивается слотом);
      * без обоих — один проход сегмента (полный цикл).
    - prefix_once — кадры до сегмента один раз перед циклом;
    - suffix_on_exit — хвост после сегмента добавляется в конец плана;
    - mirror="left" — план играть зеркально.

    durations_ms — длительности кадров клипа в порядке индексов. Если индексы
    loop выходят за границы (клип переслили), loop игнорируется с warning.
    """
    count = len(durations_ms)
    if count == 0:
        return FramePlan(())
    mirror = spec.mirror == "left"
    if spec.once:
        return FramePlan(tuple(range(count)), mirror=mirror)
    if spec.loop is None:
        loop = (0, count - 1)
    else:
        loop = spec.loop
        if loop[1] >= count:
            logger.warning(
                "Спека %r: loop=%r вне границ клипа из %d кадров — игнорируется",
                spec.name,
                list(loop),
                count,
            )
            loop = (0, count - 1)

    segment = list(range(loop[0], loop[1] + 1))
    prefix = list(range(loop[0])) if spec.prefix_once else []
    segment_ms = max(1, sum(durations_ms[index] for index in segment))
    prefix_ms = sum(durations_ms[index] for index in prefix)

    if spec.repeat_fill_ms is not None:
        target = max(1, round(spec.repeat_fill_ms / segment_ms))
        repeats = (
            rng.randint(max(1, target - 1), target + 1) if rng is not None else target
        )
        if slot_ms is not None:
            # цель не должна растягивать слот
            budget_ms = max(1, slot_ms - prefix_ms)
            repeats = min(repeats, max(1, budget_ms // segment_ms))
    elif slot_ms is not None:
        # loop крутится весь слот (состояние FSM держится времени слота)
        budget_ms = max(1, slot_ms - prefix_ms)
        repeats = max(1, budget_ms // segment_ms)
    else:
        repeats = 1

    indices = prefix + segment * repeats
    if spec.suffix_on_exit and loop[1] + 1 < count:
        indices += list(range(loop[1] + 1, count))
    return FramePlan(tuple(indices), mirror=mirror)
