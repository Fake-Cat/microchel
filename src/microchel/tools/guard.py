"""PathGuard (PHASE 5): чтение файлов только внутри разрешённых каталогов.

Все пути резолвятся (expanduser + resolve, включая symlink) и проверяются на
принадлежность allowlist-каталогам. Попытка выхода — ToolDenied, не исключение
в потоке инструмента. Запись/исполнение не предоставляются вовсе.
"""

from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path

from microchel.tools.base import ToolDenied, ToolInvalid


class PathGuard:
    """Allowlist-проверка путей: только чтение внутри разрешённых корней."""

    def __init__(self, allowed_roots: Iterable[str | Path]) -> None:
        self._roots = tuple(Path(root).expanduser().resolve() for root in allowed_roots)

    @property
    def roots(self) -> tuple[Path, ...]:
        return self._roots

    def resolve(self, raw_path: str) -> Path:
        """Резолв пути и проверка вхождения в allowlist; запрет — ToolDenied."""
        if not isinstance(raw_path, str) or not raw_path.strip():
            raise ToolInvalid("аргумент 'path' должен быть непустой строкой")
        path = Path(raw_path).expanduser().resolve()
        if not self._roots:
            raise ToolDenied(
                "чтение файлов запрещено: allowed_roots пуст (задайте каталоги в config/agent.toml)"
            )
        for root in self._roots:
            if path == root or root in path.parents:
                return path
        roots_list = ", ".join(str(root) for root in self._roots)
        raise ToolDenied(f"путь вне разрешённых каталогов: {path} (разрешены: {roots_list})")