"""Инструмент system.metrics (PHASE 5): реальные метрики компьютера.

Только чтение /proc и /sys + shutil — без LLM и без shell. Значения
недоступны → поле None, а не выдуманное число.
"""

from __future__ import annotations

import os
import shutil
from pathlib import Path
from typing import Any

from microchel.tools.base import ToolResult, ToolSpec


def _read_loadavg() -> tuple[float | None, float | None, float | None]:
    try:
        parts = Path("/proc/loadavg").read_text(encoding="utf-8").split()
        return float(parts[0]), float(parts[1]), float(parts[2])
    except (OSError, IndexError, ValueError):
        return None, None, None


def _read_meminfo() -> tuple[float | None, float | None]:
    """(MemTotal, MemAvailable) в MiB."""
    try:
        values: dict[str, int] = {}
        for line in Path("/proc/meminfo").read_text(encoding="utf-8").splitlines():
            key, _, rest = line.partition(":")
            values[key.strip()] = int(rest.strip().split()[0])
        total = values.get("MemTotal")
        available = values.get("MemAvailable")
        to_mib = lambda kb: round(kb / 1024, 1) if kb is not None else None  # noqa: E731
        return to_mib(total), to_mib(available)
    except (OSError, ValueError):
        return None, None


def _read_uptime() -> float | None:
    try:
        return float(Path("/proc/uptime").read_text(encoding="utf-8").split()[0])
    except (OSError, IndexError, ValueError):
        return None


def _read_cpu_temp() -> float | None:
    try:
        raw = Path("/sys/class/thermal/thermal_zone0/temp").read_text(encoding="utf-8").strip()
        return round(int(raw) / 1000, 1)
    except (OSError, ValueError):
        return None


class SystemMetricsTool:
    """system.metrics — load average, память, диск, uptime, температура CPU."""

    def spec(self) -> ToolSpec:
        return ToolSpec(
            name="system.metrics",
            description=(
                "Текущие метрики компьютера: load average, память, диск корневого "
                "раздела, uptime и температура CPU (если доступна). Аргументов нет."
            ),
            parameters={"type": "object", "properties": {}, "required": []},
        )

    def execute(self, arguments: dict[str, Any]) -> ToolResult:  # noqa: ARG002
        load1, load5, load15 = _read_loadavg()
        mem_total, mem_available = _read_meminfo()
        disk_total: float | None = None
        disk_free: float | None = None
        try:
            usage = shutil.disk_usage("/")
            disk_total = round(usage.total / 1024**3, 1)
            disk_free = round(usage.free / 1024**3, 1)
        except OSError:
            pass
        data = {
            "load1": load1,
            "load5": load5,
            "load15": load15,
            "mem_total_mb": mem_total,
            "mem_available_mb": mem_available,
            "disk_total_gb": disk_total,
            "disk_free_gb": disk_free,
            "uptime_s": _read_uptime(),
            "cpu_count": os.cpu_count(),
            "cpu_temp_c": _read_cpu_temp(),
        }
        return ToolResult(ok=True, data=data)