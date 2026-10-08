"""Юнит-тесты событий и шины (PHASE 3, FR-P3.6, FR-P3.7)."""

from __future__ import annotations

from dataclasses import FrozenInstanceError

import pytest

from microchel.common.event_bus import EventBus
from microchel.common.events import (
    CharacterAction,
    SystemEvent,
    SystemEventKind,
    UserEvent,
    UserEventKind,
)


class TestEventTypes:
    def test_user_event_frozen(self) -> None:
        event = UserEvent(kind=UserEventKind.CLICK)
        with pytest.raises(FrozenInstanceError):
            event.kind = UserEventKind.DRAG_START  # type: ignore[misc]

    def test_user_event_kinds(self) -> None:
        assert UserEventKind.CLICK.value == "click"
        assert UserEventKind.DRAG_START.value == "drag_start"
        assert UserEventKind.DRAG_END.value == "drag_end"

    def test_system_event_defaults(self) -> None:
        event = SystemEvent(kind=SystemEventKind.SYNTHETIC)
        assert event.payload == ""

    def test_character_action_holds_name(self) -> None:
        assert CharacterAction(action="walk").action == "walk"


class TestEventBus:
    def test_subscribe_and_emit(self) -> None:
        bus = EventBus()
        received: list[object] = []
        bus.subscribe(UserEvent, received.append)
        event = UserEvent(kind=UserEventKind.CLICK)
        bus.emit(event)
        assert received == [event]

    def test_no_subscribers_is_noop(self) -> None:
        EventBus().emit(UserEvent(kind=UserEventKind.CLICK))

    def test_emit_only_matching_type(self) -> None:
        bus = EventBus()
        user_events: list[object] = []
        system_events: list[object] = []
        bus.subscribe(UserEvent, user_events.append)
        bus.subscribe(SystemEvent, system_events.append)
        bus.emit(SystemEvent(kind=SystemEventKind.SYNTHETIC))
        assert user_events == []
        assert len(system_events) == 1

    def test_unsubscribe(self) -> None:
        bus = EventBus()
        received: list[object] = []
        handler = received.append
        bus.subscribe(UserEvent, handler)
        bus.unsubscribe(UserEvent, handler)
        bus.emit(UserEvent(kind=UserEventKind.CLICK))
        assert received == []

    def test_unsubscribe_missing_is_noop(self) -> None:
        EventBus().unsubscribe(UserEvent, lambda event: None)

    def test_duplicate_subscribe_single_call(self) -> None:
        bus = EventBus()
        calls: list[int] = []

        def handler(event: object) -> None:
            del event
            calls.append(1)

        bus.subscribe(UserEvent, handler)
        bus.subscribe(UserEvent, handler)
        bus.emit(UserEvent(kind=UserEventKind.CLICK))
        assert calls == [1]

    def test_failing_handler_does_not_break_others(self, caplog: pytest.LogCaptureFixture) -> None:
        bus = EventBus()
        received: list[object] = []

        def broken(event: object) -> None:
            del event
            raise RuntimeError("boom")

        bus.subscribe(UserEvent, broken)
        bus.subscribe(UserEvent, received.append)
        with caplog.at_level("ERROR"):
            bus.emit(UserEvent(kind=UserEventKind.CLICK))
        assert len(received) == 1
        assert any("упал" in record.message for record in caplog.records)

    def test_clear_removes_everything(self) -> None:
        bus = EventBus()
        received: list[object] = []
        bus.subscribe(UserEvent, received.append)
        bus.clear()
        bus.emit(UserEvent(kind=UserEventKind.CLICK))
        assert received == []
