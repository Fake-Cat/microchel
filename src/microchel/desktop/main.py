"""Точка входа Microchel (PHASE 1: Minimal Desktop Pet; PHASE 2: Animation Engine;
PHASE 3: Character Behavior — сборка controller, флаги --demo/--showcase/--demo-events)."""

from __future__ import annotations

import argparse
import logging
import os
import random
import sys
from collections.abc import Iterable, Mapping, Sequence

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import QApplication

from microchel.animation.queue import Priority
from microchel.animation.spec import ClipSpec
from microchel.character.config import DEFAULT_CONFIG_PATH, load_behavior_config
from microchel.character.controller import CharacterController, EdgeWalker
from microchel.character.fsm import BehaviorFSM
from microchel.character.states import STATE_CLIP_PREFIX, CharacterState
from microchel.common.event_bus import EventBus
from microchel.common.events import SystemEvent, SystemEventKind
from microchel.common.logging_config import setup_logging
from microchel.desktop.window import DEFAULT_PET_SCALE, PetWindow

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


def invisible_platform_warning(platform_name: str) -> str | None:
    """Текст предупреждения, если платформа рисует без экрана (offscreen).

    Ловит ситуацию «логи идут, окна нет»: например, QT_QPA_PLATFORM=offscreen
    в окружении запускает приложение без видимого окна — анимации при этом
    проигрываются. Возвращается текст предупреждения или None.
    """
    if platform_name == "offscreen":
        return (
            "Платформа offscreen: окно не появится на экране — "
            "проверьте QT_QPA_PLATFORM в окружении запуска"
        )
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


def start_showcase(
    window: PetWindow,
    *,
    pause_s: float = 0.0,
    speed: float = 1.0,
    walk_step_px: int = 3,
    walk_interval_ms: int = 60,
    only: str | None = None,
) -> QTimer:
    """Показать все анимации по очереди — полный лист кадров каждой (PHASE 4).

    Каждый клип играется целиком: все кадры по порядку (0..N-1), без повторов
    и обрезки по loop-сегменту (loop/repeat — рантайм-семантика FSM, не показ).
    Зеркало mirror="left" сохраняется; пауза pause_s (по умолчанию 0 — слоты
    подряд, стык плавный) и следующий клип.
    Idle-клипы не показываются отдельными слотами; фоновая idle в паузах
    выключается — в паузе держится последний кадр слота (инспекция без фона).
    motion=walk — шаги EdgeWalker с разворотом у края, motion=traverse — шаги
    до края без разворота (допущение — спека FSM ещё не утверждена).
    only — подстрока-фильтр имён (без учёта регистра): показываются только
    клипы, содержащие её; нет совпадений — показ отключается с предупреждением.
    Список клипов и спека перечитываются на каждом слоте — персонажа можно
    менять через меню прямо во время показа. Окно при этом FSM отключён,
    показываются только анимации. Переходный клип (MOVED CLIP) отключён:
    Move/Transition играет отдельным слотом цикла, а не перед каждым клипом.
    """
    window.set_transition_enabled(False)
    window.set_idle_fallback_enabled(False)  # пауза без фоновой idle — слот держится
    index = 0
    walker: EdgeWalker | None = None
    traverse_dx = 0  # шаг traverse; 0 — motion не активен

    motion_timer = QTimer(window)
    motion_timer.setInterval(max(1, walk_interval_ms))

    def motion_tick() -> None:
        if walker is not None:
            walker.step(window.move_by)
        elif traverse_dx and not window.move_by(traverse_dx):
            motion_timer.stop()  # упёрлись в край — дальше без движения

    motion_timer.timeout.connect(motion_tick)

    timer = QTimer(window)
    timer.setSingleShot(True)
    # PreciseTimer: CoarseTimer стреляет до 5% раньше срока — стык слотов
    # обрезал последний кадр (фикс стыков, 2026-10-11)
    timer.setTimerType(Qt.TimerType.PreciseTimer)

    def next_clip() -> None:
        nonlocal index, walker, traverse_dx
        # idle не показываем отдельными слотами — это «фоновая» анимация
        clips = sorted(
            name for name in window.available_clip_names() if not name.casefold().startswith("idle")
        )
        if only is not None:
            needle = only.casefold()
            clips = [name for name in clips if needle in name.casefold()]
        if not clips:
            motion_timer.stop()
            return
        index %= len(clips)
        name = clips[index]
        index += 1
        lowered = name.casefold()
        priority = Priority.EVENT if "blink" in lowered else Priority.BEHAVIOR

        spec = window.clip_specs.get(name, ClipSpec())
        durations = window.clip_durations(name)

        # motion: walk — с разворотом у края; traverse — до края без разворота
        walker = None
        traverse_dx = 0
        motion_timer.stop()
        if durations is not None and spec.motion in ("walk", "traverse"):
            direction = -1 if (spec.mirror == "left" or "left" in lowered) else 1
            if spec.motion == "walk":
                walker = EdgeWalker(walk_step_px, direction=direction)
            else:
                traverse_dx = direction * walk_step_px
            motion_timer.start()

        # план показа: полный лист кадров клипа (см. фикс 2026-10-11)
        frame_indices: Sequence[int] | None = None
        mirror = spec.mirror == "left"
        loop: bool | int = True
        slot_ms = 0
        if durations is not None:
            # полный лист кадров: показ = все кадры клипа по порядку; loop/repeat
            # спеки — рантайм-семантика FSM и показ не обрезают (фикс 2026-10-11)
            frame_indices = tuple(range(len(durations)))
            loop = False
            played_ms = sum(durations)
            slot_ms = int(played_ms / max(speed, 1e-6))

        if window.play_clip(
            name,
            priority=priority,
            loop=loop,
            restart=True,
            frame_indices=frame_indices,
            mirror=mirror,
        ):
            number = (index - 1) % len(clips) + 1
            cycle = (index - 1) // len(clips) + 1
            logger.info(
                "showcase: %s (анимация %d из %d, цикл %d, план %d кадров%s%s)",
                name,
                number,
                len(clips),
                cycle,
                len(frame_indices) if frame_indices is not None else 0,
                ", mirror" if mirror else "",
                f", motion={spec.motion}" if spec.motion != "none" else "",
            )
        timer.start(max(1, slot_ms + int(pause_s * 1000)))

    timer.timeout.connect(next_clip)
    if not window.available_clip_names():
        logger.warning("showcase: клипы не найдены, показ отключён")
        return timer
    if only is not None and not any(
        only.casefold() in name.casefold() for name in window.available_clip_names()
    ):
        logger.warning("showcase: нет клипов по маске %r — показ отключён", only)
        return timer
    next_clip()
    return timer


def states_with_clips(clip_names: Iterable[str]) -> set[CharacterState]:
    """Состояния, у которых есть хотя бы один клип (FR-P3.1: нет клипа → пропуск).

    IDLE также может отсутствовать — FSM добавит его сам, а контроллер
    предупредит в логе при попытке показать анимацию. Если не найдено ни одного
    клипа состояний (например, у малинки только Welcome) — одна info-строка
    вместо предупреждения по каждому состоянию (NF-P3.5, 2026-10-10).
    """
    names = tuple(clip_names)
    available: set[CharacterState] = set()
    for state in CharacterState:
        prefix = STATE_CLIP_PREFIX[state]
        if any(name.startswith(prefix) for name in names):
            available.add(state)
    missing = [state for state in CharacterState if state not in available]
    if not available:
        logger.info(
            "Клипы состояний не найдены (%s) — поведение не включается",
            ", ".join(f"{state.value}={STATE_CLIP_PREFIX[state]}*" for state in missing),
        )
    elif missing:
        logger.warning(
            "Клипы состояний не найдены: %s — состояния исключены",
            ", ".join(state.value for state in missing),
        )
    return available


def start_behavior(window: PetWindow, bus: EventBus) -> CharacterController | None:
    """Собрать FSM + контроллер и включить поведение (FR-P3.8, NF-P3.5).

    Вызывается только при подключённых анимациях; окно получает события из bus,
    контроллер — play/move-колбэки в окно и animation_finished для восстановления
    состояния после реакции (FR-P3.5). Возвращает None, если ни у одного
    состояния нет клипа (например, только Welcome — крутка играет как idle).
    """
    available = states_with_clips(window.available_clip_names())
    if not available:
        return None
    config = load_behavior_config(DEFAULT_CONFIG_PATH)
    fsm = BehaviorFSM(config, available=available)
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
        nargs="?",
        const=True,
        default=None,
        metavar="NAME",
        help=(
            "показать все анимации по очереди — все кадры каждой (idle не "
            "показывается); со значением NAME — только клипы, содержащие подстроку"
        ),
    )
    parser.add_argument(
        "--showcase-interval",
        type=float,
        default=0.0,
        metavar="SEC",
        help="пауза между анимациями в --showcase, секунд (по умолчанию 0 — слоты подряд)",
    )
    parser.add_argument(
        "--speed",
        type=float,
        default=1.0,
        metavar="X",
        help="скорость анимаций: 1 — норма, 0.5 — вдвое медленнее, 2 — вдвое быстрее",
    )
    parser.add_argument(
        "--pet-scale",
        type=float,
        default=DEFAULT_PET_SCALE,
        metavar="X",
        help=f"масштаб персонажа на экране (по умолчанию {DEFAULT_PET_SCALE}; 1 — натуральный)",
    )
    parser.add_argument(
        "--show-frame-stats",
        action="store_true",
        help="анализатор модели: на каждом кадре показывать bbox модели, границы кадра и масштабы",
    )
    parser.add_argument(
        "--demo-events",
        action="store_true",
        help="синтетические системные события каждые 45–90 с (проверка механики FR-P3.6)",
    )
    args = parser.parse_args(argv)
    if args.showcase_interval < 0:
        parser.error("--showcase-interval должен быть >= 0")
    if args.speed <= 0:
        parser.error("--speed должен быть > 0")
    if args.pet_scale <= 0:
        parser.error("--pet-scale должен быть > 0")
    return args


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    setup_logging(args.log_level)

    platform_choice = select_qt_platform()
    if platform_choice:
        os.environ["QT_QPA_PLATFORM"] = platform_choice
        logger.info("Wayland-сессия: запуск через XWayland (xcb) — драг и always-on-top, ADR-002")

    app = QApplication(sys.argv[:1])
    app.setApplicationName("microchel")
    logger.info("Qt platform: %s", app.platformName())
    platform_warning = invisible_platform_warning(app.platformName())
    if platform_warning:
        logger.warning(platform_warning)

    bus = EventBus()
    window = PetWindow(bus=bus, frame_stats=args.show_frame_stats)
    if args.show_frame_stats:
        logger.info("Анализатор модели включён (--show-frame-stats)")
    has_animation = window.setup_animation()
    window.set_pet_scale(args.pet_scale)
    window.set_animation_speed(args.speed)
    window.show()
    logger.info("Окно показано: %dx%d, позиция %s", window.width(), window.height(), window.pos())

    # контроллер и таймер событий держатся локальными ссылками до конца app.exec()
    controller: CharacterController | None = None
    if args.showcase is not None:
        if has_animation:
            only = args.showcase if isinstance(args.showcase, str) else None
            start_showcase(window, pause_s=args.showcase_interval, speed=args.speed, only=only)
            logger.info(
                "Showcase: %s, пауза %s с; поведение отключено",
                f"клипы по маске {only!r}" if only else "полный цикл каждой анимации",
                args.showcase_interval,
            )
        else:
            logger.warning("--showcase: анимации не подключены, показ отключён")
    elif args.demo:
        if has_animation:
            start_demo(window)
            logger.info("Демо-режим анимаций включён (каждые 4 с); поведение отключено (FR-P3.8)")
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
