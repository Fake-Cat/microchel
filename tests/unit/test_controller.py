"""Юнит-тесты EdgeWalker — разворот ходьбы у края (PHASE 3, FR-P3.4)."""

from __future__ import annotations

import pytest

from microchel.character.controller import EdgeWalker


class TestEdgeWalker:
    def test_initial_state(self) -> None:
        walker = EdgeWalker(3)
        assert walker.direction == 1
        assert walker.step_px == 3

    def test_moves_right_by_default(self) -> None:
        walker = EdgeWalker(3)
        seen: list[int] = []
        dx = walker.step(lambda d: seen.append(d) or True)
        assert dx == 3
        assert seen == [3]
        assert walker.direction == 1

    def test_blocked_edge_reverses(self) -> None:
        walker = EdgeWalker(5)
        assert walker.step(lambda d: False) == 5  # шаг сделан, но окно у края
        assert walker.direction == -1
        assert walker.step(lambda d: True) == -5  # развернулись
        assert walker.direction == -1

    def test_alternating_block_reverses_back(self) -> None:
        walker = EdgeWalker(2)
        walker.step(lambda d: False)  # → влево
        walker.step(lambda d: False)  # снова упёрлись → вправо
        assert walker.direction == 1
        assert walker.step(lambda d: True) == 2

    @pytest.mark.parametrize("step_px", [0, -3])
    def test_invalid_step_px_rejected(self, step_px: int) -> None:
        with pytest.raises(ValueError):
            EdgeWalker(step_px)
