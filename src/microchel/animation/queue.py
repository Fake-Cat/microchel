"""Приоритетная очередь запросов анимаций (FR-P2.5).

Чистая логика без Qt — тестируется юнит-тестами.
"""

from __future__ import annotations

import heapq
from dataclasses import dataclass
from enum import IntEnum
from itertools import count

from microchel.animation.frames import AnimationClip


class Priority(IntEnum):
    """Приоритеты анимаций (ARCHITECTURE.md: reaction > event > behavior > idle)."""

    IDLE = 0
    BEHAVIOR = 10
    EVENT = 20
    REACTION = 30


@dataclass(frozen=True, slots=True)
class AnimationRequest:
    """Запрос проигрывания клипа: приоритет, loop, немедленный restart."""

    clip: AnimationClip
    priority: Priority = Priority.IDLE
    loop: bool = True
    restart: bool = False


class AnimationQueue:
    """Очередь с выбором по приоритету; FIFO внутри одного приоритета."""

    def __init__(self) -> None:
        # heapq по ключу (-priority, seq): высший приоритет первым, внутри — FIFO
        self._items: list[tuple[int, int, AnimationRequest]] = []
        self._seq = count()

    def push(self, request: AnimationRequest) -> None:
        heapq.heappush(self._items, (-int(request.priority), next(self._seq), request))

    def pop_best(self) -> AnimationRequest | None:
        """Извлечь запрос с наивысшим приоритетом (или None)."""
        if not self._items:
            return None
        return heapq.heappop(self._items)[2]

    def clear(self) -> None:
        self._items.clear()

    @property
    def best_priority(self) -> Priority | None:
        """Приоритет лучшего ожидающего запроса (или None)."""
        if not self._items:
            return None
        return Priority(-self._items[0][0])

    def __len__(self) -> int:
        return len(self._items)
