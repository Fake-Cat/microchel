"""Журнал выполнения Agent Core (PHASE 5): JSONL + in-memory копия.

Каждая запись — JSON-строка (append-only). Сбой записи журнала не должен
ронять задачу: ошибка пишется в лог как warning. Путь по умолчанию —
$XDG_DATA_HOME/microchel/agent_journal.jsonl (NF: вне репозитория).
"""

from __future__ import annotations

import json
import logging
import os
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


def default_journal_path() -> Path:
    """~/.local/share/microchel/agent_journal.jsonl (с учётом XDG_DATA_HOME)."""
    base = Path(os.environ.get("XDG_DATA_HOME") or Path.home() / ".local" / "share")
    return base / "microchel" / "agent_journal.jsonl"


@dataclass(frozen=True, slots=True)
class JournalEntry:
    """Одна запись журнала: событие задачи/шага/вызова."""

    task_id: str
    event: str  # task_started | llm_call | tool_call | step | task_finished
    data: dict[str, Any] = field(default_factory=dict)
    ts: float = field(default_factory=time.time)


class ExecutionJournal:
    """Append-only журнал задач агента (файл + память для тестов)."""

    def __init__(self, path: Path | str | None = None) -> None:
        self._path = Path(path) if path is not None else None
        self._entries: list[JournalEntry] = []

    @property
    def path(self) -> Path | None:
        return self._path

    def record(self, entry: JournalEntry) -> None:
        """Записать событие; ошибка файла — warning, не исключение."""
        self._entries.append(entry)
        if self._path is None:
            return
        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            with self._path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(asdict(entry), ensure_ascii=False) + "\n")
        except OSError:
            logger.warning("Журнал недоступен для записи (%s)", self._path, exc_info=True)

    def entries(self) -> tuple[JournalEntry, ...]:
        """In-memory копия записей (хронологически)."""
        return tuple(self._entries)