"""Точка входа Microchel (PHASE 1: Minimal Desktop Pet; PHASE 2: Animation Engine;
PHASE 3: Character Behavior — сборка controller, флаги --demo/--showcase/--demo-events)."""

from __future__ import annotations

import argparse
import logging
import os
import random
import sys
from collections.abc import Iterable, Mapping

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication

from microchel.animation.queue import Priority
from microchel.character.config import DEFAULT_CONFIG_PATH, load_behavior_config
from microchel.character.controller import CharacterController
from microchel.character.fsm import BehaviorFSM
from microchel.character.states import STATE_CLIP_PREFIX, CharacterState
from microchel.common.event_bus import EventBus
from microchel.common.events import SystemEvent, SystemEventKind
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


def start_showcase(window: PetWindow, *, seconds: float = 10.0) -> QTimer:
    """Показать все клипы по очереди по seconds секунд (ручная проверка ассетов).

    Каждый слот: restart=True (немедленная замена предыдущего клипа) и
    loop=True (короткие клипы вроде blink не уходят в idle-фоллбэк до конца
    слота). После последнего клипа цикл повторяется. Окно не двигается —
    FSM отключён, показываются только анимации.
    """
    clips = sorted(
        window.available_clip_names(),
        key=lambda name: (not name.casefold().startswith("idle"), name.casefold()),
    )
    index = 0

    def next_clip() -> None:
        nonlocal index
        if not clips:
            return
        name = clips[index % len(clips)]
        index += 1
        lowered = name.casefold()
        if "idle" in lowered:
            priority = Priority.IDLE
        elif "blink" in lowered:
            priority = Priority.EVENT
        else:
            priority = Priority.BEHAVIOR
        if window.play_clip(name, priority=priority, loop=True, restart=True):
            number = (index - 1) % len(clips) + 1
            cycle = (index - 1) // len(clips) + 1
            logger.info("showcase: %s (клип %d из %d, цикл %d)", name, number, len(clips), cycle)

    timer = QTimer(window)
    timer.setInterval(max(int(seconds * 1000), 1))
    timer.timeout.connect(next_clip)
    if not clips:
        logger.warning("showcase: клипы не найдены, показ отключён")
        return timer
    next_clip()
    timer.start()
    return timer


def states_with_clips(clip_names: Iterable[str]) -> set[CharacterState]:
    """Состояния, у которых есть хотя бы один клип (FR-P3.1: нет клипа → пропуск).

    IDLE также может отсутствовать — FSM добавит его сам, а контроллер
    предупредит в логе при попытке показать анимацию.
    """
    names = tuple(clip_names)
    available: set[CharacterState] = set()
    for state in CharacterState:
        prefix = STATE_CLIP_PREFIX[state]
        if any(name.startswith(prefix) for name in names):
            available.add(state)
        else:
            logger.warning(
                "Клип состояния %s не найден (%s*) — состояние исключено", state.value, prefix
            )
    return available


def start_behavior(window: PetWindow, bus: EventBus) -> CharacterController | None:
    """Собрать FSM + контроллер и включить поведение (FR-P3.8, NF-P3.5).

    Вызывается только при подключённых анимациях; окно получает события из bus,
    контроллер — play/move-колбэки в окно и animation_finished для восстановления
    состояния после реакции (FR-P3.5).
    """
    config = load_behavior_config(DEFAULT_CONFIG_PATH)
    fsm = BehaviorFSM(config, available=states_with_clips(window.available_clip_names()))
    controller = CharacterController(
        fsm,
        bus,
        play=lambda prefix, priority, loop, restart: window.play_clip(
            prefix, priority=priority, loop=loop, restart=restart
        ),
        move_by=window.move_by,
        parent=window,
    )
    if window.player is not None:
        window.player.animation_finished.connect(controller.notify_animation_finished)
    controller.start()
    logger.info(
        "Поведение подключено: состояния=%s",
        sorted(state.value for state in fsm.available),
    )
    return controller


def start_demo_events(
    bus: EventBus,
    *,
    rng: random.Random | None = None,
    interval_ms: tuple[int, int] = (45_000, 90_000),
) -> QTimer:
    """Синтетические системные события (FR-P3.6): источник-заглушка до PHASE 7.

    Случайный интервал 45–90 с; без подписчика (controller) событие — no-op.
    """
    source = rng if rng is not None else random.Random()
    timer = QTimer()
    timer.setSingleShot(True)

    def tick() -> None:
        bus.emit(SystemEvent(kind=SystemEventKind.SYNTHETIC, payload="demo"))
        logger.info("demo-events: отправлено синтетическое системное событие")
        timer.start(source.randint(*interval_ms))

    timer.timeout.connect(tick)
    timer.start(source.randint(*interval_ms))
    return timer


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="microchel", description="Microchel desktop pet")
    parser.add_argument("--log-level", default=None, help="уровень логирования (DEBUG, INFO, ...)")
    demo_group = parser.add_mutually_exclusive_group()
    demo_group.add_argument(
        "--demo",
        action="store_true",
        help="демо-переключение анимаций каждые 4 с (визуальная проверка PHASE 2)",
    )
    demo_group.add_argument(
        "--showcase",
        action="store_true",
        help="показать все клипы по очереди по 10 с (ручная проверка ассетов)",
    )
    parser.add_argument(
        "--demo-events",
        action="store_true",
        help="синтетические системные события каждые 45–90 с (проверка механики FR-P3.6)",
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

    bus = EventBus()
    window = PetWindow(bus=bus)
    has_animation = window.setup_animation()
    window.show()
    logger.info("Окно показано: %dx%d, позиция %s", window.width(), window.height(), window.pos())

    # контроллер и таймер событий держатся локальными ссылками до конца app.exec()
    controller: CharacterController | None = None
    if args.showcase:
        if has_animation:
            start_showcase(window)
            logger.info("Showcase: все клипы по 10 с; поведение отключено")
        else:
            logger.warning("--showcase: анимации не подключены, показ отключён")
    elif args.demo:
        if has_animation:
            start_demo(window)
            logger.info(
                "Демо-режим анимаций включён (каждые 4 с); поведение отключено (FR-P3.8)"
            )
        else:
            logger.warning("--demo: анимации не подключены, демо отключено")
    elif has_animation:
        controller = start_behavior(window, bus)
    else:
        logger.info("Поведение не включено: анимации не найдены (NF-P3.5)")

    demo_events: QTimer | None = None
    if args.demo_events:
        demo_events = start_demo_events(bus)
        logger.info("--demo-events: синтетические системные события каждые 45–90 с")

    if controller is not None:
        logger.debug("controller активен: состояние=%s", controller.fsm.state.value)
    if demo_events is not None and demo_events.isActive():
        logger.debug("таймер demo-events: первый тик через %d мс", demo_events.remainingTime())

    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
