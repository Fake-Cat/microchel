"""Минимальная событийная шина (PHASE 3, FR-P3.7).

Синхронная, для главного Qt-потока: emit сразу вызывает подписчиков.
Сбой одного подписчика не прерывает остальные (ошибка — в лог).
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any

logger = logging.getLogger(__name__)

Handler = Callable[[Any], None]


class EventBus:
    """Шина событий: подписка по конкретному типу события, emit — синхронный."""

    def __init__(self) -> None:
        self._subscribers: dict[type, list[Handler]] = {}

    def subscribe(self, event_type: type, handler: Handler) -> None:
        """Подписаться на события указанного типа (повторная подписка — no-op)."""
        handlers = self._subscribers.setdefault(event_type, [])
        if handler not in handlers:
            handlers.append(handler)

    def unsubscribe(self, event_type: type, handler: Handler) -> None:
        """Отписаться; отсутствующая подписка не ошибка."""
        handlers = self._subscribers.get(event_type)
        if handlers is None:
            return
        try:
            handlers.remove(handler)
        except ValueError:
            return
        if not handlers:
            del self._subscribers[event_type]

    def emit(self, event: object) -> None:
        """Доставить событие подписчикам его типа; исключения не маскируются, а логируются."""
        for handler in tuple(self._subscribers.get(type(event), ())):
            try:
                handler(event)
            except Exception:
                logger.exception("Обработчик события %s упал", type(event).__name__)

    def clear(self) -> None:
        """Снять все подписки (тесты/остановка)."""
        self._subscribers.clear()
