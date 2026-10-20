"""Тесты FakeProvider: сценарные ответы и история вызовов."""

from microchel.agent.llm.fake import FakeProvider
from microchel.agent.types import LLMMessage, LLMResponse, ToolCall
from microchel.tools.base import ToolSpec


def test_scripted_responses_in_order() -> None:
    provider = FakeProvider(
        responses=[
            LLMResponse(
                text="", tool_calls=(ToolCall(id="c0", name="system.metrics", arguments={}),)
            ),
            LLMResponse(text="готово"),
        ]
    )
    messages = (LLMMessage(role="user", content="hi"),)
    tools = (ToolSpec(name="system.metrics", description="метрики"),)
    first = provider.complete(messages, tools)
    second = provider.complete(messages, tools)
    assert first.tool_calls[0].name == "system.metrics"
    assert second.text == "готово"
    assert provider.remaining == 0


def test_default_response_when_script_exhausted() -> None:
    provider = FakeProvider()
    response = provider.complete((), ())
    assert "офлайн" in response.text.lower()
    assert not response.tool_calls


def test_records_call_history() -> None:
    provider = FakeProvider()
    messages = (LLMMessage(role="user", content="hi"),)
    provider.complete(messages, ())
    assert len(provider.calls) == 1
    assert provider.calls[0][0] == messages