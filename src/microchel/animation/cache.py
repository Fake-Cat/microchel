"""LRU-кэш ресурсов с ограничением по памяти (NF-P2.1).

Чистая логика без Qt: загрузчик — колбэк (путь → (объект, размер_в_байтах)),
поэтому кэш тестируется юнит-тестами без QPixmap.
"""

from __future__ import annotations

from collections import OrderedDict
from collections.abc import Callable
from pathlib import Path
from typing import Generic, TypeVar

T = TypeVar("T")

Loader = Callable[[Path], tuple[T, int]]


class FrameCache(Generic[T]):
    """LRU-кэш по байтам: вытесняет самое старое при превышении лимита."""

    def __init__(self, max_bytes: int, loader: Loader[T]) -> None:
        if max_bytes <= 0:
            raise ValueError("max_bytes должен быть > 0")
        self._max_bytes = max_bytes
        self._loader = loader
        self._entries: OrderedDict[Path, tuple[T, int]] = OrderedDict()
        self._used_bytes = 0
        self.hits = 0
        self.misses = 0

    @property
    def max_bytes(self) -> int:
        return self._max_bytes

    @property
    def used_bytes(self) -> int:
        return self._used_bytes

    def __len__(self) -> int:
        return len(self._entries)

    def get(self, path: Path) -> T | None:
        """Вернуть объект из кэша (обновляя LRU), либо None."""
        entry = self._entries.get(path)
        if entry is None:
            self.misses += 1
            return None
        self._entries.move_to_end(path)
        self.hits += 1
        return entry[0]

    def load(self, path: Path) -> T:
        """Вернуть объект: из кэша или загрузив (с вытеснением старых)."""
        cached = self.get(path)
        if cached is not None:
            return cached
        obj, size = self._loader(path)
        if size > self._max_bytes:
            return obj  # объект больше лимита — показать нужно, но не храним
        while self._entries and self._used_bytes + size > self._max_bytes:
            self._evict_oldest()
        self._entries[path] = (obj, size)
        self._used_bytes += size
        return obj

    def invalidate(self, path: Path) -> None:
        """Убрать один объект из кэша."""
        entry = self._entries.pop(path, None)
        if entry is not None:
            self._used_bytes -= entry[1]

    def purge(self) -> None:
        """Полностью очистить кэш (выгрузить ресурсы)."""
        self._entries.clear()
        self._used_bytes = 0

    def _evict_oldest(self) -> None:
        _path, (_value, size) = self._entries.popitem(last=False)
        self._used_bytes -= size
