"""Тесты system.metrics: реальные значения /proc и /sys, без выдумок."""

from microchel.tools.system_metrics import SystemMetricsTool


def test_metrics_shape_on_linux() -> None:
    result = SystemMetricsTool().execute({})
    assert result.ok
    data = result.data
    expected_keys = {
        "load1",
        "load5",
        "load15",
        "mem_total_mb",
        "mem_available_mb",
        "disk_total_gb",
        "disk_free_gb",
        "uptime_s",
        "cpu_count",
        "cpu_temp_c",
    }
    assert set(data) == expected_keys
    # Значения либо корректные числа, либо None (недоступно) — но не выдуманные
    assert data["mem_total_mb"] is None or data["mem_total_mb"] > 0
    assert data["disk_total_gb"] is None or data["disk_total_gb"] > 0
    assert data["uptime_s"] is None or data["uptime_s"] > 0
    assert data["cpu_count"] is None or data["cpu_count"] >= 1


def test_metrics_ignores_arguments() -> None:
    result = SystemMetricsTool().execute({"чего_угодно": 1})
    assert result.ok