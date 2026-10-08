"""Smoke-тесты инфраструктуры (PHASE 0).

Проверяют, что пакет установлен и Qt-зависимость доступна.
GUI-логика тестируется в своих PHASE.
"""

from __future__ import annotations

import importlib


def test_package_importable() -> None:
    """Пакет microchel устанавливается и импортируется."""
    microchel = importlib.import_module("microchel")
    assert microchel.__name__ == "microchel"


def test_pyside6_core_available() -> None:
    """PySide6.QtCore импортируется из окружения проекта."""
    qtcore = importlib.import_module("PySide6.QtCore")
    assert qtcore.__name__ == "PySide6.QtCore"
