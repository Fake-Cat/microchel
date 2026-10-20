"""Тесты журнала выполнения агента: JSONL, память, устойчивость к сбоям."""

import json
from pathlib import Path

from microchel.agent.journal import ExecutionJournal, JournalEntry, default_journal_path


def test_memory_only_journal() -> None:
    journal = ExecutionJournal()
    journal.record(JournalEntry(task_id="t1", event="task_started", data={"prompt": "x"}))
    entries = journal.entries()
    assert len(entries) == 1
    assert entries[0].event == "task_started"
    assert journal.path is None


def test_journal_writes_jsonl(tmp_path: Path) -> None:
    path = tmp_path / "sub" / "journal.jsonl"
    journal = ExecutionJournal(path)
    journal.record(JournalEntry(task_id="t1", event="task_started", data={"prompt": "x"}))
    journal.record(JournalEntry(task_id="t1", event="task_finished", data={"status": "completed"}))
    lines = path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 2
    first = json.loads(lines[0])
    assert first["task_id"] == "t1"
    assert first["event"] == "task_started"
    assert "ts" in first


def test_journal_survives_unwritable_path(tmp_path: Path) -> None:
    blocker = tmp_path / "файл_вместо_каталога"
    blocker.write_text("x", encoding="utf-8")
    journal = ExecutionJournal(blocker / "nested" / "journal.jsonl")
    journal.record(JournalEntry(task_id="t1", event="step", data={}))  # не должно бросить
    assert len(journal.entries()) == 1


def test_default_journal_path_is_outside_repo() -> None:
    path = default_journal_path()
    assert path.name == "agent_journal.jsonl"
    assert "microchel" in path.parts