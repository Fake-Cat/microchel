"""Адаптер Gemini (PHASE 5): generateContent + function calling через urllib.

Формат: systemInstruction для system-сообщения, contents (user/model) для
диалога, functionDeclarations из ToolSpec, thoughtSignature витков tool call
возвращается провайдеру как есть (требование Gemini для «thinking» моделей).
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from typing import Any

from microchel.agent.llm.base import (
    LLMAuthError,
    LLMNetworkError,
    LLMProtocolError,
    LLMRateLimitError,
)
from microchel.agent.llm.http import HttpClient
from microchel.agent.types import LLMMessage, LLMResponse, ToolCall
from microchel.tools.base import ToolSpec

DEFAULT_BASE_URL = "https://generativelanguage.googleapis.com/v1beta"


class GeminiProvider:
    """Провайдер Gemini: единый complete() поверх REST generateContent."""

    name = "gemini"

    def __init__(
        self,
        api_key: str,
        model: str = "gemini-3.8-flash",
        *,
        proxy_url: str = "",
        base_url: str = "",
        http: HttpClient | None = None,
        timeout_s: float = 60.0,
    ) -> None:
        self._api_key = api_key
        self._model = model
        self._base_url = (base_url or DEFAULT_BASE_URL).rstrip("/")
        self._http = (
            http if http is not None else HttpClient(proxy_url=proxy_url, timeout_s=timeout_s)
        )

    def complete(self, messages: Sequence[LLMMessage], tools: Sequence[ToolSpec]) -> LLMResponse:
        payload = self._build_payload(messages, tools)
        url = f"{self._base_url}/models/{self._model}:generateContent"
        status, data = self._http.post_json(
            url,
            payload,
            headers={"x-goog-api-key": self._api_key},
        )
        self._raise_for_status(status, data)
        return self._parse_response(data)

    # --- запрос ---

    def _build_payload(
        self, messages: Sequence[LLMMessage], tools: Sequence[ToolSpec]
    ) -> dict[str, Any]:
        contents: list[dict[str, Any]] = []
        system_texts: list[str] = []
        for message in messages:
            if message.role == "system":
                system_texts.append(message.content)
            elif message.role == "user":
                contents.append({"role": "user", "parts": [{"text": message.content}]})
            elif message.role == "assistant":
                parts: list[dict[str, Any]] = []
                if message.content:
                    parts.append({"text": message.content})
                for call in message.tool_calls:
                    function_part: dict[str, Any] = {
                        "functionCall": {"name": call.name, "args": call.arguments}
                    }
                    if call.signature:
                        # thoughtSignature живёт на уровне part, а не внутри functionCall
                        function_part["thoughtSignature"] = call.signature
                    parts.append(function_part)
                contents.append({"role": "model", "parts": parts})
            elif message.role == "tool":
                contents.append(
                    {
                        "role": "user",
                        "parts": [
                            {
                                "functionResponse": {
                                    "name": message.name,
                                    "response": _response_payload(message),
                                }
                            }
                        ],
                    }
                )
        payload: dict[str, Any] = {"contents": contents}
        if system_texts:
            payload["systemInstruction"] = {"parts": [{"text": "\n".join(system_texts)}]}
        if tools:
            payload["tools"] = [
                {
                    "functionDeclarations": [
                        {
                            "name": spec.name,
                            "description": spec.description,
                            "parameters": spec.parameters or {"type": "object", "properties": {}},
                        }
                        for spec in tools
                    ]
                }
            ]
        return payload

    def _raise_for_status(self, status: int, data: dict[str, Any]) -> None:
        if status == 200:
            return
        message = _error_message(data)
        if status in (401, 403):
            raise LLMAuthError(f"Gemini {status}: {message}")
        if status == 429:
            raise LLMRateLimitError(f"Gemini 429: {message}")
        if status >= 500:
            raise LLMNetworkError(f"Gemini {status}: {message}")
        raise LLMProtocolError(f"Gemini {status}: {message}")

    # --- ответ ---

    def _parse_response(self, data: dict[str, Any]) -> LLMResponse:
        candidates = data.get("candidates") or []
        if not candidates:
            raise LLMProtocolError(f"Gemini: пустой ответ (нет candidates): {str(data)[:500]}")
        parts = (candidates[0].get("content") or {}).get("parts") or []
        text_pieces: list[str] = []
        calls: list[ToolCall] = []
        for part in parts:
            if "text" in part:
                text_pieces.append(str(part["text"]))
            function_call = part.get("functionCall")
            if function_call:
                calls.append(
                    ToolCall(
                        id=f"call_{len(calls)}",
                        name=str(function_call.get("name", "")),
                        arguments=dict(function_call.get("args") or {}),
                        signature=str(
                            part.get("thoughtSignature")
                            or function_call.get("thoughtSignature")
                            or ""
                        ),
                    )
                )
        return LLMResponse(
            text="".join(text_pieces),
            tool_calls=tuple(calls),
            finish_reason=str(candidates[0].get("finishReason", "")),
            model=str(data.get("modelVersion", self._model)),
        )


def _response_payload(message: LLMMessage) -> dict[str, Any]:
    """functionResponse.response обязан быть JSON-объектом."""
    try:
        parsed = json.loads(message.content) if message.content else {}
    except json.JSONDecodeError:
        return {"text": message.content}
    return parsed if isinstance(parsed, dict) else {"result": parsed}


def _error_message(data: dict[str, Any]) -> str:
    error = data.get("error")
    if isinstance(error, dict):
        return str(error.get("message", error))
    return str(data)[:500]