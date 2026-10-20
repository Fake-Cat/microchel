"""HTTP-клиент Agent Core (PHASE 5): stdlib urllib, прокси, ретраи.

Без новых зависимостей (в aarch64 любой wheel — это риск; urllib везде есть).
Прокси-резолюция (ADR-006): CLI --proxy > config.proxy_url > https_proxy/
http_proxy окружения/.env > прямое подключение. Ретрай на 429/503 — один.
"""

from __future__ import annotations

import json
import logging
import time
import urllib.error
import urllib.request
from collections.abc import Callable
from typing import Any

from microchel.agent.llm.base import LLMNetworkError

logger = logging.getLogger(__name__)

RETRY_STATUS = (429, 503)
DEFAULT_RETRY_DELAY_S = 3.0


class HttpClient:
    """Минимальный JSON-over-HTTP: post_json/get_json → (status, dict)."""

    def __init__(
        self,
        proxy_url: str = "",
        timeout_s: float = 60.0,
        *,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self._timeout_s = timeout_s
        self._sleep = sleep
        handlers: list[urllib.request.BaseHandler] = []
        if proxy_url:
            handlers.append(urllib.request.ProxyHandler({"http": proxy_url, "https": proxy_url}))
        self._opener = urllib.request.build_opener(*handlers)

    def post_json(
        self,
        url: str,
        payload: dict[str, Any],
        headers: dict[str, str] | None = None,
    ) -> tuple[int, dict[str, Any]]:
        """POST JSON с одним ретраем на 429/503; сетевые сбои → LLMNetworkError."""
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        request_headers = {"Content-Type": "application/json", **(headers or {})}
        for attempt in range(2):
            status, raw = self._send(url, data=body, headers=request_headers)
            if status in RETRY_STATUS and attempt == 0:
                logger.warning(
                    "HTTP %s от %s — повтор через %.1f с", status, url, DEFAULT_RETRY_DELAY_S
                )
                self._sleep(DEFAULT_RETRY_DELAY_S)
                continue
            return status, raw
        raise LLMNetworkError(f"HTTP-запрос к {url} не выполнен")

    def get_json(
        self, url: str, headers: dict[str, str] | None = None
    ) -> tuple[int, dict[str, Any]]:
        """GET JSON; сетевые сбои → LLMNetworkError."""
        return self._send(url, data=None, headers=headers or {})

    def _send(
        self,
        url: str,
        *,
        data: bytes | None,
        headers: dict[str, str],
    ) -> tuple[int, dict[str, Any]]:
        request = urllib.request.Request(
            url, data=data, headers=headers, method="POST" if data else "GET"
        )
        try:
            with self._opener.open(request, timeout=self._timeout_s) as response:
                status = response.getcode()
                raw = response.read().decode("utf-8", errors="replace")
        except urllib.error.HTTPError as error:  # 4xx/5xx — это статус, не падение сети
            raw = error.read().decode("utf-8", errors="replace")
            return error.code, _try_json(raw)
        except (urllib.error.URLError, TimeoutError, OSError) as error:
            raise LLMNetworkError(f"сеть недоступна ({url}): {error}") from error
        return status, _try_json(raw)


def _try_json(raw: str) -> dict[str, Any]:
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return {"_raw": raw[:2000]}
    return parsed if isinstance(parsed, dict) else {"_raw": parsed}