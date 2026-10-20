"""Инструменты files.* (PHASE 5): чтение файлов и листинг каталогов.

Только чтение внутри allowed_roots через PathGuard — без записи, без
исполнения, без следования symlink наружу. Бинарные файлы не отдаются.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from microchel.tools.base import ToolError, ToolResult, ToolSpec
from microchel.tools.guard import PathGuard

DEFAULT_MAX_BYTES = 32768
MAX_BYTES_CAP = 262144


class ReadFileTool:
    """files.read_file — чтение текстового файла внутри allowed_roots."""

    def __init__(self, guard: PathGuard) -> None:
        self._guard = guard

    def spec(self) -> ToolSpec:
        return ToolSpec(
            name="files.read_file",
            description=(
                "Прочитать текстовый файл внутри разрешённых каталогов. "
                "Аргументы: path (путь к файлу), max_bytes (необязательно, лимит чтения)."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Путь к файлу"},
                    "max_bytes": {
                        "type": "integer",
                        "description": "Сколько байт читать (по умолчанию 32768)",
                    },
                },
                "required": ["path"],
            },
        )

    def execute(self, arguments: dict[str, Any]) -> ToolResult:
        try:
            path = self._guard.resolve(str(arguments["path"]))
            max_bytes = int(arguments.get("max_bytes", DEFAULT_MAX_BYTES))
            max_bytes = max(1, min(max_bytes, MAX_BYTES_CAP))
            if not path.is_file():
                return ToolResult(ok=False, error=f"не файл: {path}")
            size = path.stat().st_size
            with path.open("rb") as handle:
                raw = handle.read(max_bytes)
        except ToolError as error:
            return ToolResult(ok=False, error=str(error))
        except (OSError, ValueError) as error:
            return ToolResult(ok=False, error=f"ошибка чтения: {error}")
        if b"\x00" in raw[:8192]:
            return ToolResult(ok=False, error="бинарный файл — чтение текста не поддерживается")
        return ToolResult(
            ok=True,
            data={
                "path": str(path),
                "size": size,
                "truncated": size > len(raw),
                "text": raw.decode("utf-8", errors="replace"),
            },
        )


class ListDirTool:
    """files.list_dir — листинг каталога внутри allowed_roots."""

    def __init__(self, guard: PathGuard) -> None:
        self._guard = guard

    def spec(self) -> ToolSpec:
        return ToolSpec(
            name="files.list_dir",
            description=(
                "Показать содержимое каталога внутри разрешённых каталогов. "
                "Аргументы: path (путь к каталогу)."
            ),
            parameters={
                "type": "object",
                "properties": {"path": {"type": "string", "description": "Путь к каталогу"}},
                "required": ["path"],
            },
        )

    def execute(self, arguments: dict[str, Any]) -> ToolResult:
        try:
            path = self._guard.resolve(str(arguments["path"]))
            if not path.is_dir():
                return ToolResult(ok=False, error=f"не каталог: {path}")
            entries = []
            for item in sorted(Path(path).iterdir(), key=lambda p: (not p.is_file(), p.name)):
                entry: dict[str, Any] = {"name": item.name, "is_dir": item.is_dir()}
                if item.is_file():
                    try:
                        entry["size"] = item.stat().st_size
                    except OSError:
                        entry["size"] = None
                entries.append(entry)
        except ToolError as error:
            return ToolResult(ok=False, error=str(error))
        except OSError as error:
            return ToolResult(ok=False, error=f"ошибка чтения каталога: {error}")
        return ToolResult(ok=True, data={"path": str(path), "entries": entries})