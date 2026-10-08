"""Юнит-тесты конфига поведения (PHASE 3, FR-P3.3)."""

from __future__ import annotations

from pathlib import Path

from microchel.character.config import (
    DEFAULT_CONFIG_PATH,
    BehaviorConfig,
    load_behavior_config,
)
from microchel.character.states import CharacterState


class TestDefaults:
    def test_none_path_returns_defaults(self) -> None:
        assert load_behavior_config(None) == BehaviorConfig()

    def test_missing_file_returns_defaults(self, tmp_path: Path) -> None:
        assert load_behavior_config(tmp_path / "nope.toml") == BehaviorConfig()

    def test_broken_toml_returns_defaults(self, tmp_path: Path) -> None:
        path = tmp_path / "behavior.toml"
        path.write_text("так это не toml [", encoding="utf-8")
        assert load_behavior_config(path) == BehaviorConfig()

    def test_duration_pairs_valid(self) -> None:
        config = BehaviorConfig()
        for state in CharacterState:
            low, high = config.duration_ms(state)
            assert low <= high

    def test_weight_idle_is_zero(self) -> None:
        assert BehaviorConfig().weight(CharacterState.IDLE) == 0

    def test_default_weights_positive(self) -> None:
        config = BehaviorConfig()
        for state in CharacterState:
            if state is CharacterState.IDLE:
                continue
            assert config.weight(state) > 0

    def test_default_config_file_exists_and_loads(self) -> None:
        # DEFAULT_CONFIG_PATH — реальный файл репозитория; его значения совпадают с дефолтами кода
        assert load_behavior_config(DEFAULT_CONFIG_PATH) == BehaviorConfig()


class TestOverrides:
    def test_valid_values_override(self, tmp_path: Path) -> None:
        path = tmp_path / "behavior.toml"
        path.write_text(
            "\n".join(
                [
                    "[idle]",
                    "min_ms = 1000",
                    "max_ms = 2000",
                    "[weights]",
                    "walk = 99",
                    "[night]",
                    "from = 22",
                    "to = 7",
                    "[reaction]",
                    'clip = "Wink"',
                ]
            ),
            encoding="utf-8",
        )
        config = load_behavior_config(path)
        assert config.duration_ms(CharacterState.IDLE) == (1000, 2000)
        assert config.weight(CharacterState.WALK) == 99
        assert (config.night_from, config.night_to) == (22, 7)
        assert config.reaction_clip == "Wink"

    def test_invalid_type_skipped(self, tmp_path: Path) -> None:
        path = tmp_path / "behavior.toml"
        path.write_text('[idle]\nmin_ms = "много"\n', encoding="utf-8")
        config = load_behavior_config(path)
        assert config.idle_min_ms == BehaviorConfig().idle_min_ms

    def test_bool_is_not_int(self, tmp_path: Path) -> None:
        path = tmp_path / "behavior.toml"
        path.write_text("[idle]\nmin_ms = true\n", encoding="utf-8")
        assert load_behavior_config(path).idle_min_ms == BehaviorConfig().idle_min_ms

    def test_out_of_range_skipped(self, tmp_path: Path) -> None:
        path = tmp_path / "behavior.toml"
        path.write_text("[night]\nfrom = 24\n", encoding="utf-8")
        assert load_behavior_config(path).night_from == BehaviorConfig().night_from

    def test_zero_duration_skipped(self, tmp_path: Path) -> None:
        path = tmp_path / "behavior.toml"
        path.write_text("[walk]\nmin_ms = 0\n", encoding="utf-8")
        assert load_behavior_config(path).walk_min_ms == BehaviorConfig().walk_min_ms

    def test_min_greater_than_max_resets_pair(self, tmp_path: Path) -> None:
        path = tmp_path / "behavior.toml"
        path.write_text("[sit]\nmin_ms = 900000\nmax_ms = 1000\n", encoding="utf-8")
        config = load_behavior_config(path)
        assert config.duration_ms(CharacterState.SIT) == (
            BehaviorConfig().sit_min_ms,
            BehaviorConfig().sit_max_ms,
        )

    def test_empty_reaction_clip_skipped(self, tmp_path: Path) -> None:
        path = tmp_path / "behavior.toml"
        path.write_text('[reaction]\nclip = "  "\n', encoding="utf-8")
        assert load_behavior_config(path).reaction_clip == BehaviorConfig().reaction_clip

    def test_unknown_sections_ignored(self, tmp_path: Path) -> None:
        path = tmp_path / "behavior.toml"
        path.write_text("[future]\nkey = 1\n", encoding="utf-8")
        assert load_behavior_config(path) == BehaviorConfig()
