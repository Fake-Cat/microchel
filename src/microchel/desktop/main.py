"""Точка входа Microchel (PHASE 1: Minimal Desktop Pet)."""

from __future__ import annotations

import argparse
import logging
import os
import sys
from collections.abc import Mapping

from PySide6.QtWidgets import QApplication

from microchel.common.logging_config import setup_logging
from microchel.desktop.window import PetWindow

logger = logging.getLogger(__name__)


def select_qt_platform(env: Mapping[str, str] | None = None) -> str | None:
    """Выбрать Qt-платформу: под Wayland-сессией по умолчанию — xcb (XWayland).

    Нативный Wayland запрещает окну менять свою позицию, а питомец обязан
    перетаскиваться (ADR-002, подтверждено проверкой в PHASE 1). Явно заданный
    пользователем QT_QPA_PLATFORM никогда не перетирается.
    """
    source = os.environ if env is None else env
    if source.get("QT_QPA_PLATFORM"):
        return None
    session = source.get("XDG_SESSION_TYPE", "").lower()
    if session == "wayland" or source.get("WAYLAND_DISPLAY"):
        return "xcb"
    return None


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="microchel", description="Microchel desktop pet")
    parser.add_argument("--log-level", default=None, help="уровень логирования (DEBUG, INFO, ...)")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    setup_logging(args.log_level)

    platform_choice = select_qt_platform()
    if platform_choice:
        os.environ["QT_QPA_PLATFORM"] = platform_choice
        logger.info(
            "Wayland-сессия: запуск через XWayland (xcb) — драг и always-on-top, ADR-002"
        )

    app = QApplication(sys.argv[:1])
    app.setApplicationName("microchel")
    logger.info("Qt platform: %s", app.platformName())

    window = PetWindow()
    window.show()
    logger.info("Окно показано: %dx%d, позиция %s", window.width(), window.height(), window.pos())

    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
