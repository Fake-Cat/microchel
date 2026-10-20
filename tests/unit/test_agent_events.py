"""Тесты событий Agent Core через общий EventBus (синхронный)."""

from dataclasses import FrozenInstanceError

import pytest

from microchel.common.event_bus import EventBus
from microchel.common.events import AgentTaskFinished, AgentTaskStarted, UserPrompt


def test_user_prompt_event() -> None:
    event = UserPrompt(text="проверь компьютер")
    assert event.text == "проверь компьютер"
    with pytest.raises(FrozenInstanceError):
        event.text = "другое"  # type: ignore[misc]


def test_agent_task_events_flow() -> None:
    bus = EventBus()
    received: list[object] = []
    bus.subscribe(UserPrompt, lambda event: received.append(event))
    bus.subscribe(AgentTaskStarted, lambda event: received.append(event))
    bus.subscribe(AgentTaskFinished, lambda event: received.append(event))
    bus.emit(UserPrompt(text="задача"))
    bus.emit(AgentTaskStarted(task_id="t1"))
    bus.emit(AgentTaskFinished(task_id="t1", status="completed"))
    assert isinstance(received[0], UserPrompt)
    assert isinstance(received[1], AgentTaskStarted)
    assert received[1].task_id == "t1"
    assert isinstance(received[2], AgentTaskFinished)
    assert received[2].status == "completed"