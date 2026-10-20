"""Инструменты агента (PHASE 5): безопасные read-only действия.

build_default_registry — сборка реестра по умолчанию для CLI и executor.
"""

from microchel.tools.base import Tool, ToolError, ToolInvalid, ToolResult, ToolSpec
from microchel.tools.file_read import ListDirTool, ReadFileTool
from microchel.tools.guard import PathGuard
from microchel.tools.registry import ToolRegistry
from microchel.tools.services import ServiceStatusTool
from microchel.tools.system_metrics import SystemMetricsTool

__all__ = [
    "ListDirTool",
    "PathGuard",
    "ReadFileTool",
    "ServiceStatusTool",
    "SystemMetricsTool",
    "Tool",
    "ToolError",
    "ToolInvalid",
    "ToolRegistry",
    "ToolResult",
    "ToolSpec",
    "build_default_registry",
]


def build_default_registry(
    allowed_roots: tuple[str, ...] = (),
    *,
    runner: object = None,
) -> ToolRegistry:
    """Реестр по умолчанию: system.metrics, files.read_file, files.list_dir, services.status.

    runner — подмена subprocess.run для тестов (см. services.ServiceStatusTool).
    """
    guard = PathGuard(allowed_roots)
    registry = ToolRegistry()
    registry.register(SystemMetricsTool())
    registry.register(ReadFileTool(guard))
    registry.register(ListDirTool(guard))
    registry.register(
        ServiceStatusTool(runner=runner) if runner is not None else ServiceStatusTool()
    )
    return registry
