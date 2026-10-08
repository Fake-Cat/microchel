"""Юнит-тесты LRU-кэша ресурсов (PHASE 2, NF-P2.1)."""

from __future__ import annotations

from pathlib import Path

import pytest

from microchel.animation.cache import FrameCache

OBJECT_SIZE = 100


def make_cache(max_bytes: int) -> tuple[FrameCache[str], list[Path]]:
    """Кэш с фейковым загрузчиком: объект = имя файла, размер = 100 байт."""
    loaded: list[Path] = []

    def loader(path: Path) -> tuple[str, int]:
        loaded.append(path)
        return f"obj:{path.name}", OBJECT_SIZE

    return FrameCache(max_bytes, loader), loaded


class TestFrameCache:
    def test_invalid_max_bytes_rejected(self) -> None:
        with pytest.raises(ValueError):
            FrameCache(0, lambda path: ("x", 1))

    def test_load_and_hit(self) -> None:
        cache, loaded = make_cache(1000)
        path = Path("a.png")
        assert cache.load(path) == "obj:a.png"
        assert cache.load(path) == "obj:a.png"  # повторно из кэша
        assert loaded == [path]  # загрузчик вызван один раз
        assert cache.hits == 1
        assert cache.misses == 1
        assert len(cache) == 1
        assert cache.used_bytes == OBJECT_SIZE

    def test_evicts_oldest_when_full(self) -> None:
        cache, _ = make_cache(250)  # влезает ровно 2 объекта
        a, b, c = Path("a.png"), Path("b.png"), Path("c.png")
        cache.load(a)
        cache.load(b)
        cache.load(c)  # вытесняет a
        assert cache.get(a) is None
        assert cache.get(b) is not None
        assert cache.get(c) is not None
        assert cache.used_bytes <= 250
        assert len(cache) == 2

    def test_get_refreshes_recency(self) -> None:
        cache, _ = make_cache(250)
        a, b, c = Path("a.png"), Path("b.png"), Path("c.png")
        cache.load(a)
        cache.load(b)
        assert cache.get(a) is not None  # a снова «свежий»
        cache.load(c)  # вытесняется b, а не a
        assert cache.get(a) is not None
        assert cache.get(b) is None

    def test_oversized_object_not_cached(self) -> None:
        cache, loaded = make_cache(50)  # лимит меньше объекта
        path = Path("big.png")
        assert cache.load(path) == "obj:big.png"  # показать-то надо!
        assert len(cache) == 0
        assert cache.used_bytes == 0
        assert cache.load(path) in ("obj:big.png",)  # снова загрузился
        assert len(loaded) == 2

    def test_purge_clears_everything(self) -> None:
        cache, _ = make_cache(1000)
        cache.load(Path("a.png"))
        cache.purge()
        assert len(cache) == 0
        assert cache.used_bytes == 0

    def test_invalidate_single_entry(self) -> None:
        cache, _ = make_cache(1000)
        a, b = Path("a.png"), Path("b.png")
        cache.load(a)
        cache.load(b)
        cache.invalidate(a)
        assert cache.get(a) is None
        assert cache.get(b) is not None
        assert cache.used_bytes == OBJECT_SIZE

    def test_many_switches_memory_stable(self) -> None:
        """1000 переключений не растят память выше лимита (NF-P2.1)."""
        cache, _ = make_cache(500)
        for i in range(1000):
            cache.load(Path(f"f{i % 10}.png"))
            assert cache.used_bytes <= 500
