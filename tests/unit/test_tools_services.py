"""Тесты services.status: фиксированный argv, валидация имён, shell=False."""

from types import SimpleNamespace
from typing import Any

from microchel.tools.services import ServiceStatusTool


class _RecordingRunner:
    def __init__(self, stdout: str = "ActiveState=active\n", returncode: int = 0) -> None:
        self.calls: list[tuple[list[str], dict[str, Any]]] = []
        self._stdout = stdout
        self._returncode = returncode

    def __call__(self, argv: list[str], **kwargs: Any) -> SimpleNamespace:
        self.calls.append((list(argv), kwargs))
        return SimpleNamespace(stdout=self._stdout, returncode=self._returncode)


def test_status_success() -> None:
    runner = _RecordingRunner(
        "ActiveState=active\nSubState=running\nDescription=OpenSSH\nMainPID=123\nLoadState=loaded\n"
    )
    result = ServiceStatusTool(runner=runner).execute({"name": "ssh"})
    assert result.ok
    assert result.data == {
        "service": "ssh",
        "active_state": "active",
        "sub_state": "running",
        "description": "OpenSSH",
        "main_pid": "123",
    }
    argv, kwargs = runner.calls[0]
    assert argv[0] == "systemctl"
    assert argv[2] == "ssh"
    assert kwargs["shell"] is False
    assert not any("sudo" in part for part in argv)


def test_rejects_injection_names() -> None:
    runner = _RecordingRunner()
    tool = ServiceStatusTool(runner=runner)
    for bad in ("foo; rm -rf /", "a b", "$(reboot)", "имя", "x" * 300):
        result = tool.execute({"name": bad})
        assert not result.ok, bad
        assert "недопустимое имя" in result.error
    assert runner.calls == []  # ни один вызов не дошёл до subprocess


def test_not_found_service() -> None:
    runner = _RecordingRunner("ActiveState=inactive\nLoadState=not-found\n")
    result = ServiceStatusTool(runner=runner).execute({"name": "ghost-service"})
    assert not result.ok
    assert "не найден" in result.error


def test_no_systemctl() -> None:
    def _missing_runner(argv: list[str], **kwargs: Any) -> SimpleNamespace:  # noqa: ARG001
        raise FileNotFoundError("systemctl")

    result = ServiceStatusTool(runner=_missing_runner).execute({"name": "ssh"})
    assert not result.ok
    assert "systemctl недоступен" in result.error