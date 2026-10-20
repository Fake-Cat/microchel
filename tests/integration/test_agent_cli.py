"""Интеграционные тесты CLI агента: офлайн-демо, ошибки, независимость от Qt."""

import json
import os
import subprocess
import sys
from pathlib import Path

from microchel.agent import cli

REPO_ROOT = Path(__file__).resolve().parents[2]


def test_offline_demo_completed(tmp_path: Path, capsys: object) -> None:
    code = cli.main(
        [
            "--offline",
            "--journal",
            str(tmp_path / "journal.jsonl"),
            "Проверь",
            "состояние",
            "компьютера",
        ]
    )
    captured = capsys.readouterr()  # type: ignore[attr-defined]
    assert code == 0
    assert "Офлайн-демо" in captured.out
    assert "статус=completed" in captured.err


def test_offline_demo_json_output(tmp_path: Path, capsys: object) -> None:
    code = cli.main(["--offline", "--json", "--journal", str(tmp_path / "j.jsonl"), "тест"])
    captured = capsys.readouterr()  # type: ignore[attr-defined]
    assert code == 0
    payload = json.loads(captured.out)
    assert payload["status"] == "completed"
    assert payload["tool_calls"] == 1
    assert payload["steps"][0]["tool_calls"][0]["name"] == "system.metrics"


def test_missing_api_key_clear_error(tmp_path: Path, monkeypatch: object, capsys: object) -> None:
    monkeypatch.setenv("GEMINI_API_KEY", "")  # type: ignore[attr-defined]
    code = cli.main(["--provider", "gemini", "--journal", str(tmp_path / "j.jsonl"), "тест"])
    captured = capsys.readouterr()  # type: ignore[attr-defined]
    assert code == 1
    assert "Ошибка конфигурации" in captured.err
    assert "GEMINI_API_KEY" in captured.err


def test_agent_modules_never_import_qt() -> None:
    env = {**os.environ, "PYTHONPATH": str(REPO_ROOT / "src")}
    script = (
        "import microchel.agent.cli, microchel.agent.executor, microchel.tools, sys; "
        "print('PySide6' in sys.modules)"
    )
    completed = subprocess.run(
        [sys.executable, "-c", script],
        capture_output=True,
        text=True,
        env=env,
        timeout=60,
    )
    assert completed.returncode == 0, completed.stderr
    assert completed.stdout.strip() == "False"