"""Интеграционный тест источника синтетических событий (--demo-events, FR-P3.6)."""

from __future__ import annotations

import random

from pytestqt.qtbot import QtBot

from microchel.common.event_bus import EventBus
from microchel.common.events import SystemEvent, SystemEventKind
from microchel.desktop.main import start_demo_events


def test_demo_events_emits_synthetic(qtbot: QtBot) -> None:
    bus = EventBus()
    received: list[SystemEvent] = []
    bus.subscribe(SystemEvent, received.append)
    timer = start_demo_events(bus, rng=random.Random(1), interval_ms=(10, 20))
    try:
        qtbot.waitUntil(lambda: len(received) >= 1, timeout=2000)
        assert received[0].kind is SystemEventKind.SYNTHETIC
        assert received[0].payload == "demo"
    finally:
        timer.stop()
        del timer
