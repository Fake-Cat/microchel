"""Инструмент services.status (PHASE 5): состояние systemd-юнита.

Безопасность: shell=False, argv фиксированный, имя юнита валидируется regex,
sudo и произвольные команды исключены. Если systemctl недоступен — явная
ошибка, не заглушка. subprocess.run вынесен в конструктор для тестов.
"""

from __future__ import annotations

import re
import subprocess
from collections.abc import Callable
from typing import Any

from microchel.tools.base import ToolResult, ToolSpec

SERVICE_NAME_RE = re.compile(r"^[A-Za-z0-9@_.\-]+$")

_SHOW_FIELDS = ("ActiveState", "SubState", "Description", "MainPID", "LoadState")


class ServiceStatusTool:
    """services.status — состояние сервиса через `systemctl show` (read-only)."""

    def __init__(self, runner: Callable[..., Any] | None = None) -> None:
        self._runner = runner if runner is not None else subprocess.run

    def spec(self) -> ToolSpec:
        return ToolSpec(
            name="services.status",
            description=(
                "Состояние системного сервиса (systemd): активность, подсостояние, "
                "описание, главный PID. Аргументы: name (имя сервиса, например ssh)."
            ),
            parameters={
                "type": "object",
                "properties": {"name": {"type": "string", "description": "Имя сервиса"}},
                "required": ["name"],
            },
        )

    def execute(self, arguments: dict[str, Any]) -> ToolResult:
        name = str(arguments["name"]).strip()
        if not name or len(name) > 256 or not SERVICE_NAME_RE.fullmatch(name):
            return ToolResult(ok=False, error=f"недопустимое имя сервиса: {name!r}")
        argv = ["systemctl", "show", name, "--no-pager", *(f"--property={f}" for f in _SHOW_FIELDS)]
        try:
            completed = self._runner(  # shell=False — фиксированный argv, без sudo
                argv,
                capture_output=True,
                text=True,
                timeout=10.0,
                shell=False,
            )
        except FileNotFoundError:
            return ToolResult(ok=False, error="systemctl недоступен в этой системе")
        except subprocess.SubprocessError as error:
            return ToolResult(ok=False, error=f"ошибка systemctl: {error}")
        fields: dict[str, str] = {}
        for line in completed.stdout.splitlines():
            key, _, value = line.partition("=")
            if key:
                fields[key.strip()] = value.strip()
        if fields.get("LoadState") == "not-found":
            return ToolResult(ok=False, error=f"сервис не найден: {name}")
        return ToolResult(
            ok=True,
            data={
                "service": name,
                "active_state": fields.get("ActiveState"),
                "sub_state": fields.get("SubState"),
                "description": fields.get("Description"),
                "main_pid": fields.get("MainPID"),
            },
        )