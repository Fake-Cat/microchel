"""Юнит-тесты приоритетной очереди анимаций (PHASE 2, FR-P2.5)."""

from __future__ import annotations

from pathlib import Path

from microchel.animation.frames import AnimationClip, FrameSpec
from microchel.animation.queue import AnimationQueue, AnimationRequest, Priority


def make_clip(name: str) -> AnimationClip:
    frame = FrameSpec(index=0, duration_ms=100, path=Path(name))
    return AnimationClip(name=name, line=1, frames=(frame,))


class TestAnimationQueue:
    def test_empty_queue(self) -> None:
        queue = AnimationQueue()
        assert queue.pop_best() is None
        assert len(queue) == 0
        assert queue.best_priority is None

    def test_fifo_within_priority(self) -> None:
        queue = AnimationQueue()
        first = AnimationRequest(clip=make_clip("a"), priority=Priority.IDLE)
        second = AnimationRequest(clip=make_clip("b"), priority=Priority.IDLE)
        queue.push(first)
        queue.push(second)
        assert queue.pop_best() is first
        assert queue.pop_best() is second

    def test_higher_priority_first(self) -> None:
        queue = AnimationQueue()
        idle = AnimationRequest(clip=make_clip("idle"), priority=Priority.IDLE)
        event = AnimationRequest(clip=make_clip("event"), priority=Priority.EVENT)
        reaction = AnimationRequest(clip=make_clip("reaction"), priority=Priority.REACTION)
        behavior = AnimationRequest(clip=make_clip("behavior"), priority=Priority.BEHAVIOR)
        for request in (idle, event, reaction, behavior):
            queue.push(request)
        assert queue.pop_best() is reaction
        assert queue.pop_best() is event
        assert queue.pop_best() is behavior
        assert queue.pop_best() is idle

    def test_best_priority_reports_next(self) -> None:
        queue = AnimationQueue()
        queue.push(AnimationRequest(clip=make_clip("x"), priority=Priority.EVENT))
        assert queue.best_priority == Priority.EVENT
        queue.pop_best()
        assert queue.best_priority is None

    def test_clear(self) -> None:
        queue = AnimationQueue()
        queue.push(AnimationRequest(clip=make_clip("x")))
        queue.clear()
        assert len(queue) == 0
        assert queue.pop_best() is None

    def test_priority_values_order(self) -> None:
        # модель ARCHITECTURE.md: reaction > event > behavior > idle
        assert Priority.REACTION > Priority.EVENT > Priority.BEHAVIOR > Priority.IDLE
