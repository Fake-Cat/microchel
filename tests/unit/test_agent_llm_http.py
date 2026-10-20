"""Тесты HttpClient (urllib): JSON, ретраи 429/503, сетевые ошибки."""

import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Any

import pytest

from microchel.agent.llm.base import LLMNetworkError
from microchel.agent.llm.http import HttpClient


class _Handler(BaseHTTPRequestHandler):
    queue: list[tuple[int, dict[str, Any]]] = []
    received: list[dict[str, Any]] = []

    def do_POST(self) -> None:  # noqa: N802 — интерфейс BaseHTTPRequestHandler
        body = self.rfile.read(int(self.headers.get("Content-Length", 0)))
        type(self).received.append(json.loads(body))
        status, payload = type(self).queue.pop(0) if type(self).queue else (200, {"ok": True})
        data = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, *args: Any) -> None:  # noqa: ARG002
        pass


@pytest.fixture()
def server() -> Any:
    _Handler.queue = []
    _Handler.received = []
    httpd = HTTPServer(("127.0.0.1", 0), _Handler)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{httpd.server_address[1]}/api"
    httpd.shutdown()
    thread.join(timeout=2)


def test_post_json_success(server: str) -> None:
    status, data = HttpClient().post_json(server, {"q": "привет"})
    assert status == 200
    assert data == {"ok": True}
    assert _Handler.received == [{"q": "привет"}]


def test_retries_on_429(server: str) -> None:
    _Handler.queue = [(429, {"error": "rate"}), (200, {"ok": True})]
    sleeps: list[float] = []
    status, data = HttpClient(sleep=sleeps.append).post_json(server, {"q": 1})
    assert status == 200
    assert data == {"ok": True}
    assert sleeps == [3.0]


def test_non_json_body_is_wrapped(server: str) -> None:
    _Handler.queue = [(200, {"_raw": "не json, но json-словарь вернётся"})]
    status, data = HttpClient().post_json(server, {})
    assert status == 200
    assert "_raw" in data


def test_network_error_raises() -> None:
    client = HttpClient(proxy_url="", timeout_s=1.0)
    with pytest.raises(LLMNetworkError):
        client.post_json("http://127.0.0.1:1/dead", {})