"""Юнит-тесты playback-спеки: загрузка clips.toml и план показа (PHASE 4)."""

from __future__ import annotations

import logging
import random
from pathlib import Path

import pytest

from microchel.animation.spec import ClipSpec, FramePlan, load_clip_specs, plan_frames

SPEC_LOGGER = "microchel.animation.spec"


def write_spec(tmp_path: Path, text: str) -> Path:
    path = tmp_path / "clips.toml"
    path.write_text(text, encoding="utf-8")
    return path


class TestLoadClipSpecs:
    def test_missing_file_returns_empty(self, tmp_path: Path) -> None:
        assert load_clip_specs(tmp_path / "clips.toml") == {}

    def test_valid_sections_parsed(self, tmp_path: Path) -> None:
        path = write_spec(
            tmp_path,
            """
[clips."Walk/Left"]
frames = 12
loop = [2, 10]
motion = "walk"

[clips."Angry/Normal"]
frames = 12
loop = [4, 10]
repeat_fill_ms = 4000

[clips."Walk/Direct"]
frames = 12
loop = [2, 10]
mirror = "left"
motion = "walk"

[clips."Idle/Normal"]
frames = 12
once = true
""",
        )
        specs = load_clip_specs(path)
        assert set(specs) == {"Walk/Left", "Angry/Normal", "Walk/Direct", "Idle/Normal"}
        assert specs["Walk/Left"].loop == (2, 10)
        assert specs["Walk/Left"].motion == "walk"
        assert specs["Walk/Left"].scale == 1.0  # дефолт
        assert specs["Angry/Normal"].repeat_fill_ms == 4000
        assert specs["Walk/Direct"].mirror == "left"
        assert specs["Idle/Normal"].once is True

    def test_loop_out_of_bounds_ignored(self, tmp_path: Path) -> None:
        path = write_spec(tmp_path, '[clips."A/B"]\nframes = 5\nloop = [3, 9]\n')
        specs = load_clip_specs(path)
        assert specs["A/B"].loop is None

    def test_invalid_fields_fall_back_to_defaults(
        self, tmp_path: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        path = write_spec(
            tmp_path,
            '[clips."A/B"]\nframes = 5\nloop = [1]\nmirror = "up"\n'
            'motion = "fly"\nrepeat_fill_ms = -1\nscale = 0\nonce = 1\n',
        )
        with caplog.at_level(logging.WARNING, logger=SPEC_LOGGER):
            specs = load_clip_specs(path)
        spec = specs["A/B"]
        assert spec.loop is None
        assert spec.mirror is None
        assert spec.motion == "none"
        assert spec.repeat_fill_ms is None
        assert spec.scale == 1.0
        assert spec.once is False
        warnings = [
            record
            for record in caplog.records
            if record.name == SPEC_LOGGER and record.levelno == logging.WARNING
        ]
        assert len(warnings) >= 6

    def test_broken_toml_returns_empty(self, tmp_path: Path) -> None:
        path = write_spec(tmp_path, "clips = [не-томл")
        assert load_clip_specs(path) == {}

    def test_broken_readme_no_clips_section(self, tmp_path: Path) -> None:
        path = write_spec(tmp_path, "other = 1\n")
        assert load_clip_specs(path) == {}


class TestPlanFrames:
    DURATIONS = (100, 100, 100, 100)

    def test_empty_clip(self) -> None:
        assert plan_frames(ClipSpec(), []) == FramePlan(())

    def test_once_single_pass_even_with_long_slot(self) -> None:
        spec = ClipSpec(name="Idle/Normal", once=True)
        plan = plan_frames(spec, self.DURATIONS, slot_ms=10_000)
        assert plan.indices == (0, 1, 2, 3)

    def test_loop_segment_repeats_to_fill_slot(self) -> None:
        spec = ClipSpec(name="Talk/Normal", loop=(1, 2))
        plan = plan_frames(spec, self.DURATIONS, slot_ms=500)
        # сегмент (1, 2) = 200 мс; floor(500/200)=2 повтора — план не дольше слота
        assert plan.indices == (1, 2, 1, 2)

    def test_no_loop_repeats_whole_clip(self) -> None:
        spec = ClipSpec(name="NoSpec")
        plan = plan_frames(spec, self.DURATIONS, slot_ms=450)
        assert plan.indices == (0, 1, 2, 3)

    def test_without_slot_and_fill_single_pass(self) -> None:
        spec = ClipSpec(name="Coffee/Normal", loop=(0, 1))
        plan = plan_frames(spec, self.DURATIONS)
        assert plan.indices == (0, 1)

    def test_repeat_fill_random_near_target(self) -> None:
        spec = ClipSpec(name="Angry/Normal", loop=(0, 1), repeat_fill_ms=400)
        plan = plan_frames(spec, self.DURATIONS, rng=random.Random(42))
        # цель 400 мс / сегмент 200 мс → 2 повтора ±1
        assert 2 <= len(plan.indices) <= 6
        assert set(plan.indices) <= {0, 1}

    def test_repeat_fill_capped_by_slot(self) -> None:
        spec = ClipSpec(name="Angry/Normal", loop=(0, 1), repeat_fill_ms=40_000)
        plan = plan_frames(spec, self.DURATIONS, slot_ms=500, rng=random.Random(42))
        assert plan.indices == (0, 1, 0, 1)

    def test_prefix_once_before_segment(self) -> None:
        spec = ClipSpec(name="Wake", loop=(2, 3), prefix_once=True)
        plan = plan_frames(spec, self.DURATIONS, slot_ms=500)
        assert plan.indices == (0, 1, 2, 3)

    def test_suffix_on_exit_appended(self) -> None:
        spec = ClipSpec(name="Sleep/Wake", loop=(0, 1), suffix_on_exit=True)
        plan = plan_frames(spec, self.DURATIONS, slot_ms=250)
        assert plan.indices == (0, 1, 2, 3)

    def test_mirror_flag(self) -> None:
        plan = plan_frames(ClipSpec(name="Walk/Direct", loop=(1, 2), mirror="left"), self.DURATIONS)
        assert plan.mirror is True
        assert plan.indices == (1, 2)
        plan_plain = plan_frames(ClipSpec(name="Walk/Right", loop=(1, 2)), self.DURATIONS)
        assert plan_plain.mirror is False

    def test_loop_out_of_bounds_at_runtime_falls_back(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Клип переслили, а спека осталась: loop игнорируется, весь клип."""
        spec = ClipSpec(name="Old/Clip", loop=(1, 9))
        with caplog.at_level(logging.WARNING, logger=SPEC_LOGGER):
            plan = plan_frames(spec, self.DURATIONS, slot_ms=150)
        assert plan.indices == (0, 1, 2, 3)
        assert any(record.name == SPEC_LOGGER for record in caplog.records)
