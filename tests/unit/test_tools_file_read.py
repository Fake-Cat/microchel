"""Тесты files.read_file и files.list_dir: allowlist, бинарь, обрезка."""

from pathlib import Path

from microchel.tools.file_read import ListDirTool, ReadFileTool
from microchel.tools.guard import PathGuard


def _tools(tmp_path: Path) -> tuple[ReadFileTool, ListDirTool]:
    guard = PathGuard([str(tmp_path)])
    return ReadFileTool(guard), ListDirTool(guard)


def test_read_text_file(tmp_path: Path) -> None:
    reader, _ = _tools(tmp_path)
    target = tmp_path / "note.txt"
    target.write_text("строка один\nстрока два", encoding="utf-8")
    result = reader.execute({"path": str(target)})
    assert result.ok
    assert result.data["text"] == "строка один\nстрока два"
    assert result.data["size"] == target.stat().st_size
    assert not result.data["truncated"]


def test_read_truncates_by_max_bytes(tmp_path: Path) -> None:
    reader, _ = _tools(tmp_path)
    target = tmp_path / "big.txt"
    target.write_text("х" * 1000, encoding="utf-8")
    result = reader.execute({"path": str(target), "max_bytes": 10})
    assert result.ok
    assert len(result.data["text"]) <= 10
    assert result.data["truncated"]


def test_read_rejects_binary(tmp_path: Path) -> None:
    reader, _ = _tools(tmp_path)
    target = tmp_path / "data.bin"
    target.write_bytes(b"\x00\x01\x02binary")
    result = reader.execute({"path": str(target)})
    assert not result.ok
    assert "бинарный" in result.error


def test_read_denies_outside(tmp_path: Path) -> None:
    root = tmp_path / "root"
    root.mkdir()
    reader, _ = _tools(root)
    result = reader.execute({"path": "/etc/passwd"})
    assert not result.ok
    assert "вне разрешённых" in result.error


def test_read_missing_file(tmp_path: Path) -> None:
    reader, _ = _tools(tmp_path)
    result = reader.execute({"path": str(tmp_path / "нет.txt")})
    assert not result.ok


def test_list_dir(tmp_path: Path) -> None:
    _, lister = _tools(tmp_path)
    (tmp_path / "каталог").mkdir()
    (tmp_path / "a.txt").write_text("x", encoding="utf-8")
    result = lister.execute({"path": str(tmp_path)})
    assert result.ok
    names = [entry["name"] for entry in result.data["entries"]]
    assert names == ["a.txt", "каталог"]  # файлы раньше каталогов
    assert result.data["entries"][0]["size"] == 1


def test_list_dir_denies_outside(tmp_path: Path) -> None:
    root = tmp_path / "root"
    root.mkdir()
    _, lister = _tools(root)
    result = lister.execute({"path": "/"})
    assert not result.ok