"""Точка входа Microchel (PHASE 1: Minimal Desktop Pet; PHASE 2: Animation Engine)."""

from __future__ import annotations

import argparse
import logging
import os
import random
import sys
from collections.abc import Mapping

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication

from microchel.animation.queue import Priority
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


def start_demo(window: PetWindow, interval_ms: int = 4000) -> QTimer:
    """Демо-переключение анимаций для визуальной проверки PHASE 2 (FR-P2.4, FR-P2.5).

    Периодически случайно запрашивает не-idle клип: blink (EVENT, один раз),
    walk (BEHAVIOR, 2 прохода) — после завершения плеер сам возвращается к idle.
    """
    timer = QTimer(window)
    timer.setInterval(interval_ms)

    def step() -> None:
        names = [name for name in window.available_clip_names() if "idle" not in name.casefold()]
        if not names:
            return
        name = random.choice(names)
        lowered = name.casefold()
        priority = Priority.EVENT if "blink" in lowered else Priority.BEHAVIOR
        loop: bool | int = 2 if "walk" in lowered else False
        if window.play_clip(name, priority=priority, loop=loop):
            logger.info("demo: запрошена анимация %s (priority=%s)", name, priority.name)

    timer.timeout.connect(step)
    timer.start()
    return timer


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="microchel", description="Microchel desktop pet")
    parser.add_argument("--log-level", default=None, help="уровень логирования (DEBUG, INFO, ...)")
    parser.add_argument(
        "--demo",
        action="store_true",
        help="демо-переключение анимаций каждые 4 с (визуальная проверка PHASE 2)",
    )
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
    has_animation = window.setup_animation()
    window.show()
    logger.info("Окно показано: %dx%d, позиция %s", window.width(), window.height(), window.pos())

    if args.demo:
        if has_animation:
            start_demo(window)
            logger.info("Демо-режим анимаций включён (каждые 4 с)")
        else:
            logger.warning("--demo: анимации не подключены, демо отключено")

    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
