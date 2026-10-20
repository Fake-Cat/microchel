"""Тесты GeminiProvider: сборка запроса, парсинг, коды ошибок."""

from typing import Any

import pytest

from microchel.agent.llm.base import (
    LLMAuthError,
    LLMNetworkError,
    LLMProtocolError,
    LLMRateLimitError,
)
from microchel.agent.llm.gemini import GeminiProvider
from microchel.agent.types import LLMMessage, ToolCall
from microchel.tools.base import ToolSpec


class _StubHttp:
    def __init__(self, status: int, data: dict[str, Any]) -> None:
        self.status = status
        self.data = data
        self.requests: list[tuple[str, dict[str, Any], dict[str, str]]] = []

    def post_json(
        self, url: str, payload: dict[str, Any], headers: dict[str, str]
    ) -> tuple[int, dict[str, Any]]:
        self.requests.append((url, payload, headers))
        return self.status, self.data


def _provider(status: int = 200, data: dict[str, Any] | None = None) -> GeminiProvider:
    if data is None:
        data = {
            "candidates": [
                {
                    "content": {
                        "role": "model",
                        "parts": [{"text": "Готово.", "thoughtSignature": "sig"}],
                    },
                    "finishReason": "STOP",
                }
            ],
            "modelVersion": "gemini-3.8-flash",
        }
    return GeminiProvider(api_key="k1", model="gemini-3.8-flash", http=_StubHttp(status, data))


def test_text_response_parsed() -> None:
    provider = _provider()
    response = provider.complete((LLMMessage(role="user", content="привет"),), ())
    assert response.text == "Готово."
    assert response.tool_calls == ()
    assert response.finish_reason == "STOP"
    assert response.model == "gemini-3.8-flash"


def test_request_shape_and_headers() -> None:
    stub = _StubHttp(200, {"candidates": [{"content": {"parts": [{"text": "ok"}]}}]})
    provider = GeminiProvider(api_key="секрет", http=stub)
    provider.complete(
        (
            LLMMessage(role="system", content="правила"),
            LLMMessage(role="user", content="привет"),
        ),
        (
            ToolSpec(
                name="system.metrics",
                description="метрики",
                parameters={"type": "object", "properties": {}},
            ),
        ),
    )
    url, payload, headers = stub.requests[0]
    assert url.endswith("/models/gemini-3.8-flash:generateContent")
    assert headers == {"x-goog-api-key": "секрет"}
    assert payload["systemInstruction"] == {"parts": [{"text": "правила"}]}
    assert payload["contents"][0] == {"role": "user", "parts": [{"text": "привет"}]}
    declarations = payload["tools"][0]["functionDeclarations"]
    assert declarations[0]["name"] == "system.metrics"


def test_function_call_parsed_with_signature() -> None:
    data = {
        "candidates": [
            {
                "content": {
                    "role": "model",
                    "parts": [
                        {
                            "functionCall": {
                                "name": "system.metrics",
                                "args": {},
                            },
                            "thoughtSignature": "sig123",
                        }
                    ],
                },
                "finishReason": "STOP",
            }
        ]
    }
    response = _provider(data=data).complete((LLMMessage(role="user", content="проверь"),), ())
    call = response.tool_calls[0]
    assert call.name == "system.metrics"
    assert call.signature == "sig123"
    assert call.arguments == {}


def test_history_with_tool_results_round_trips_signature() -> None:
    stub = _StubHttp(200, {"candidates": [{"content": {"parts": [{"text": "ответ"}]}}]})
    provider = GeminiProvider(api_key="k", http=stub)
    provider.complete(
        (
            LLMMessage(role="user", content="проверь"),
            LLMMessage(
                role="assistant",
                tool_calls=(
                    ToolCall(id="c0", name="system.metrics", arguments={}, signature="sig123"),
                ),
            ),
            LLMMessage(
                role="tool",
                name="system.metrics",
                tool_call_id="c0",
                content='{"ok": true, "data": {"a": 1}}',
            ),
        ),
        (),
    )
    contents = stub.requests[0][1]["contents"]
    model_part = contents[1]["parts"][0]
    assert model_part["thoughtSignature"] == "sig123"
    function_response = contents[2]["parts"][0]["functionResponse"]
    assert function_response["name"] == "system.metrics"
    assert function_response["response"] == {"ok": True, "data": {"a": 1}}


@pytest.mark.parametrize(
    ("status", "exc"),
    [
        (401, LLMAuthError),
        (403, LLMAuthError),
        (429, LLMRateLimitError),
        (500, LLMNetworkError),
        (400, LLMProtocolError),
    ],
)
def test_error_mapping(status: int, exc: type[Exception]) -> None:
    provider = _provider(status=status, data={"error": {"message": "нет"}})
    with pytest.raises(exc):
        provider.complete((LLMMessage(role="user", content="x"),), ())


def test_empty_candidates_is_protocol_error() -> None:
    provider = _provider(data={"candidates": []})
    with pytest.raises(LLMProtocolError):
        provider.complete((LLMMessage(role="user", content="x"),), ())