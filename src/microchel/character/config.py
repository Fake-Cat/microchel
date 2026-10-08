"""Конфигурация поведения (PHASE 3, FR-P3.3): config/behavior.toml.

Дефолты живут в dataclass; файл TOML (tomllib, stdlib) их перекрывает.
Битый/отсутствующий файл или невалидные значения → дефолты + предупреждение
в лог, не крах. Чистая логика без Qt — тестируется юнит-тестами.
"""

from __future__ import annotations

import logging
import tomllib
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

from microchel.character.states import CharacterState

logger = logging.getLogger(__name__)

DEFAULT_CONFIG_PATH = Path(__file__).resolve().parents[3] / "config" / "behavior.toml"


@dataclass(frozen=True, slots=True)
class BehaviorConfig:
    """Тайминги, веса и параметры ходьбы; все значения — миллисекунды/пиксели."""

    idle_min_ms: int = 15_000
    idle_max_ms: int = 60_000
    walk_min_ms: int = 5_000
    walk_max_ms: int = 15_000
    sit_min_ms: int = 60_000
    sit_max_ms: int = 180_000
    coffee_min_ms: int = 30_000
    coffee_max_ms: int = 60_000
    thinking_min_ms: int = 20_000
    thinking_max_ms: int = 45_000
    sleep_min_ms: int = 300_000
    sleep_max_ms: int = 900_000
    weight_walk: int = 40
    weight_sit: int = 20
    weight_coffee: int = 15
    weight_thinking: int = 15
    weight_sleep: int = 10
    night_from: int = 23
    night_to: int = 8
    night_sleep_weight: int = 300
    walk_step_px: int = 3
    walk_interval_ms: int = 60
    reaction_clip: str = "Blink"

    def duration_ms(self, state: CharacterState) -> tuple[int, int]:
        """(min, max) длительности состояния — для random.Random.randint."""
        fields = _DURATION_FIELDS[state]
        return getattr(self, fields[0]), getattr(self, fields[1])

    def weight(self, state: CharacterState) -> int:
        """Вес автономного выбора состояния (0 — исключено из выбора)."""
        if state is CharacterState.IDLE:
            return 0
        return getattr(self, _WEIGHT_FIELDS[state])


# поля BehaviorConfig для пар min/max и весов
_DURATION_FIELDS: dict[CharacterState, tuple[str, str]] = {
    CharacterState.IDLE: ("idle_min_ms", "idle_max_ms"),
    CharacterState.WALK: ("walk_min_ms", "walk_max_ms"),
    CharacterState.SIT: ("sit_min_ms", "sit_max_ms"),
    CharacterState.COFFEE: ("coffee_min_ms", "coffee_max_ms"),
    CharacterState.THINKING: ("thinking_min_ms", "thinking_max_ms"),
    CharacterState.SLEEP: ("sleep_min_ms", "sleep_max_ms"),
}

_WEIGHT_FIELDS: dict[CharacterState, str] = {
    CharacterState.WALK: "weight_walk",
    CharacterState.SIT: "weight_sit",
    CharacterState.COFFEE: "weight_coffee",
    CharacterState.THINKING: "weight_thinking",
    CharacterState.SLEEP: "weight_sleep",
}


# (секция TOML, ключ, поле BehaviorConfig, минимум, максимум|None)
_INT_KEYS: tuple[tuple[str, str, str, int, int | None], ...] = (
    ("idle", "min_ms", "idle_min_ms", 1, None),
    ("idle", "max_ms", "idle_max_ms", 1, None),
    ("walk", "min_ms", "walk_min_ms", 1, None),
    ("walk", "max_ms", "walk_max_ms", 1, None),
    ("walk", "step_px", "walk_step_px", 1, None),
    ("walk", "interval_ms", "walk_interval_ms", 1, None),
    ("sit", "min_ms", "sit_min_ms", 1, None),
    ("sit", "max_ms", "sit_max_ms", 1, None),
    ("coffee", "min_ms", "coffee_min_ms", 1, None),
    ("coffee", "max_ms", "coffee_max_ms", 1, None),
    ("thinking", "min_ms", "thinking_min_ms", 1, None),
    ("thinking", "max_ms", "thinking_max_ms", 1, None),
    ("sleep", "min_ms", "sleep_min_ms", 1, None),
    ("sleep", "max_ms", "sleep_max_ms", 1, None),
    ("weights", "walk", "weight_walk", 0, None),
    ("weights", "sit", "weight_sit", 0, None),
    ("weights", "coffee", "weight_coffee", 0, None),
    ("weights", "thinking", "weight_thinking", 0, None),
    ("weights", "sleep", "weight_sleep", 0, None),
    ("night", "from", "night_from", 0, 23),
    ("night", "to", "night_to", 0, 23),
    ("night", "sleep_weight", "night_sleep_weight", 0, None),
)


def _read_int(
    raw: dict[str, Any],
    section: str,
    key: str,
    minimum: int,
    maximum: int | None,
) -> int | None:
    """Валидное int-значение из секции TOML или None (с предупреждением в лог)."""
    section_data = raw.get(section)
    if not isinstance(section_data, dict):
        return None
    value = section_data.get(key)
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int):
        logger.warning("Конфиг поведения: %s.%s — ожидалось число, пропущено", section, key)
        return None
    if value < minimum or (maximum is not None and value > maximum):
        high = maximum if maximum is not None else "inf"
        logger.warning(
            "Конфиг поведения: %s.%s=%s вне [%s, %s], пропущено", section, key, value, minimum, high
        )
        return None
    return value


def _config_from_raw(raw: dict[str, Any]) -> BehaviorConfig:
    """Собрать конфиг из разобранного TOML: валидные значения перекрывают дефолты."""
    overrides: dict[str, int] = {}
    for section, key, field_name, minimum, maximum in _INT_KEYS:
        value = _read_int(raw, section, key, minimum, maximum)
        if value is not None:
            overrides[field_name] = value

    reaction = raw.get("reaction")
    if isinstance(reaction, dict):
        clip = reaction.get("clip")
        if isinstance(clip, str) and clip.strip():
            overrides["reaction_clip"] = clip.strip()
        elif clip is not None:
            logger.warning("Конфиг поведения: reaction.clip — ожидалась строка, пропущено")

    return _fix_duration_pairs(replace(BehaviorConfig(), **overrides))


def _fix_duration_pairs(config: BehaviorConfig) -> BehaviorConfig:
    """min > max → пара сбрасывается к дефолту (защита от randint-крашей)."""
    defaults = BehaviorConfig()
    for state, (min_field, max_field) in _DURATION_FIELDS.items():
        if getattr(config, min_field) <= getattr(config, max_field):
            continue
        logger.warning(
            "Конфиг поведения: min > max для %s (%s > %s) — пара сброшена к дефолту",
            state.value,
            min_field,
            max_field,
        )
        config = replace(
            config,
            **{min_field: getattr(defaults, min_field), max_field: getattr(defaults, max_field)},
        )
    return config


def load_behavior_config(path: Path | None = None) -> BehaviorConfig:
    """Загрузить конфиг поведения; любые проблемы → дефолты + лог (FR-P3.3)."""
    if path is None:
        return BehaviorConfig()
    if not path.is_file():
        logger.info("Конфиг поведения не найден (%s) — используются дефолты", path)
        return BehaviorConfig()
    try:
        raw = tomllib.loads(path.read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError) as error:
        logger.warning("Конфиг поведения не прочитан (%s: %s) — дефолты", path, error)
        return BehaviorConfig()
    return _config_from_raw(raw)
