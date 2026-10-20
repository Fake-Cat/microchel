"""Тесты PathGuard: allowlist, symlink-выходы, пустые корни."""

from pathlib import Path

import pytest

from microchel.tools.base import ToolDenied, ToolInvalid
from microchel.tools.guard import PathGuard


def test_resolves_inside_root(tmp_path: Path) -> None:
    guard = PathGuard([str(tmp_path)])
    target = tmp_path / "sub" / "file.txt"
    target.parent.mkdir()
    target.write_text("x", encoding="utf-8")
    assert guard.resolve(str(target)) == target.resolve()


def test_denies_outside_root(tmp_path: Path) -> None:
    root = tmp_path / "root"
    root.mkdir()
    guard = PathGuard([str(root)])
    with pytest.raises(ToolDenied):
        guard.resolve("/etc/passwd")


def test_denies_with_empty_roots() -> None:
    guard = PathGuard([])
    with pytest.raises(ToolDenied):
        guard.resolve("/tmp/что-нибудь")


def test_denies_symlink_escape(tmp_path: Path) -> None:
    root = tmp_path / "root"
    root.mkdir()
    outside = tmp_path / "снаружи.txt"
    outside.write_text("x", encoding="utf-8")
    link = root / "ссылка.txt"
    link.symlink_to(outside)
    guard = PathGuard([str(root)])
    with pytest.raises(ToolDenied):
        guard.resolve(str(link))


def test_expanduser_resolves_home() -> None:
    guard = PathGuard(["~"])
    resolved = guard.resolve("~/файл.txt")
    assert resolved == (Path.home() / "файл.txt").resolve()


def test_rejects_empty_path() -> None:
    guard = PathGuard(["/tmp"])
    with pytest.raises(ToolInvalid):
        guard.resolve("  ")