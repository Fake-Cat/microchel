"""Настройка логирования Microchel."""

from __future__ import annotations

import logging
import os
import sys

LOG_FORMAT = "%(asctime)s %(levelname)-7s %(name)s: %(message)s"
DATE_FORMAT = "%H:%M:%S"


def setup_logging(level: str | None = None) -> None:
    """Настроить структурированный вывод логов в stderr.

    Уровень берётся из аргумента, затем из MICROCHEL_LOG_LEVEL, затем INFO.
    """
    resolved = level or os.environ.get("MICROCHEL_LOG_LEVEL", "INFO")
    logging.basicConfig(
        level=getattr(logging, resolved.upper(), logging.INFO),
        format=LOG_FORMAT,
        datefmt=DATE_FORMAT,
        stream=sys.stderr,
        force=True,
    )
