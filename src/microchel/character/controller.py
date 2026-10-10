"""Контроллер поведения (PHASE 3): Qt-клей FSM, event bus, плеера и окна.

Таймер состояния (сколько пробыть) и таймер шага ходьбы — QTimer в главном
потоке (NF-P3.2). События шины → FSM → смена состояния → play(клип)/move_by(dx).
Логика разворота у края (EdgeWalker) — чистая, тестируется без Qt (NF-P3.1).
"""

from __future__ import annotations

import logging
from collections.abc import Callable

from PySide6.QtCore import QObject, QTimer

from microchel.animation.queue import Priority
from microchel.character.fsm import BehaviorFSM
from microchel.character.states import STATE_PRIORITY, CharacterState, clip_prefix_for
from microchel.common.event_bus import EventBus
from microchel.common.events import CharacterAction, SystemEvent, UserEvent, UserEventKind

logger = logging.getLogger(__name__)

# колбэк проигрывания: (префикс клипа, приоритет, loop, restart) → клип найден/запрошен
PlayFn = Callable[[str, Priority, bool | int, bool], bool]
# колбэк сдвига окна на dx пикселей по X: True — позиция изменилась
MoveFn = Callable[[int], bool]


class EdgeWalker:
    """Шаг ходьбы с разворотом у края (FR-P3.4): сдвиг не удался → меняем направление."""

    def __init__(self, step_px: int, direction: int = 1) -> None:
        if step_px < 1:
            raise ValueError(f"step_px должен быть >= 1: {step_px}")
        if direction not in (-1, 1):
            raise ValueError(f"direction должен быть 1 или -1: {direction}")
        self._step_px = step_px
        self._direction = direction

    @property
    def direction(self) -> int:
        return self._direction

    @property
    def step_px(self) -> int:
        return self._step_px

    def step(self, move_by: MoveFn) -> int:
        """Один шаг ходьбы; возвращает выполненный dx (для логов и тестов)."""
        dx = self._direction * self._step_px
        if not move_by(dx):
            self._direction = -self._direction
            logger.debug("Ходьба: позиция не изменилась, разворот → %s", self._direction)
        return dx


class CharacterController(QObject):
    """Связывает FSM + bus + плеер + окно: таймеры, события, play/move (FR-P3.x)."""

    def __init__(
        self,
        fsm: BehaviorFSM,
        bus: EventBus,
        *,
        play: PlayFn,
        move_by: MoveFn,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._fsm = fsm
        self._bus = bus
        self._play = play
        self._move_by = move_by
        self._walker = EdgeWalker(fsm.config.walk_step_px)
        self._started = False
        self._reaction_active = False

        self._state_timer = QTimer(self)
        self._state_timer.setSingleShot(True)
        self._state_timer.timeout.connect(self._on_state_timeout)
        self._walk_timer = QTimer(self)
        self._walk_timer.setInterval(max(1, fsm.config.walk_interval_ms))
        self._walk_timer.timeout.connect(self._on_walk_tick)

    # --- состояние -----------------------------------------------------

    @property
    def fsm(self) -> BehaviorFSM:
        return self._fsm

    @property
    def started(self) -> bool:
        return self._started

    @property
    def reaction_active(self) -> bool:
        """True, пока играет реакция на клик (состояние при этом не меняется)."""
        return self._reaction_active

    # --- жизненный цикл ------------------------------------------------

    def start(self) -> None:
        """Подписаться на события и запустить поведение из текущего состояния FSM."""
        if self._started:
            return
        self._started = True
        self._bus.subscribe(UserEvent, self._on_user_event)
        self._bus.subscribe(SystemEvent, self._on_system_event)
        logger.info("Поведение запущено (состояние: %s)", self._fsm.state.value)
        self._apply_state()

    def stop(self) -> None:
        """Остановить таймеры и отписаться (окно и плеер остаются как есть)."""
        if not self._started:
            return
        self._started = False
        self._state_timer.stop()
        self._walk_timer.stop()
        self._reaction_active = False
        self._bus.unsubscribe(UserEvent, self._on_user_event)
        self._bus.unsubscribe(SystemEvent, self._on_system_event)
        logger.info("Поведение остановлено")

    # --- события шины --------------------------------------------------

    def _on_user_event(self, event: UserEvent) -> None:
        new_state = self._fsm.on_user_event(event.kind)
        if new_state is not None:
            # драг прервал ходьбу (FR-P3.5) — немедленный переход в idle
            self._apply_state()
            return
        if event.kind is UserEventKind.CLICK:
            self._play_reaction()

    def _on_system_event(self, event: SystemEvent) -> None:
        """Синтетическое событие (FR-P3.6): реакция с приоритетом EVENT."""
        logger.info("Системное событие: %s %s", event.kind.value, event.payload)
        if not self._play(self._fsm.config.reaction_clip, Priority.EVENT, False, False):
            logger.warning(
                "Системное событие: реакция %s недоступна", self._fsm.config.reaction_clip
            )

    # --- реакция на клик -----------------------------------------------

    def _play_reaction(self) -> None:
        """CLICK → краткая реакция поверх состояния (FR-P3.5)."""
        if self._reaction_active:
            return  # повторный клик не стакается
        if self._play(self._fsm.config.reaction_clip, Priority.REACTION, False, False):
            self._reaction_active = True
            logger.debug("Клик: реакция поверх состояния %s", self._fsm.state.value)

    def notify_animation_finished(self, name: str) -> None:
        """player.animation_finished: однократная анимация кончилась → вернуть состояние.

        State-клипы играют loop=True и не завершаются сами, поэтому любое завершение —
        конец реакции/события: возобновляем клип текущего состояния (FR-P3.5).
        Подключается снаружи: player.animation_finished.connect(controller...).
        """
        if not self._started:
            return
        if name.startswith(self._fsm.config.reaction_clip):
            self._reaction_active = False
        self._play_state_clip()

    # --- таймеры -------------------------------------------------------

    def _on_state_timeout(self) -> None:
        self._fsm.on_timeout()
        self._apply_state()

    def _on_walk_tick(self) -> None:
        self._walker.step(self._move_by)

    # --- применение состояния ------------------------------------------

    def _apply_state(self) -> None:
        state = self._fsm.state
        duration = max(1, self._fsm.state_duration_ms())
        self._state_timer.start(duration)
        if state is CharacterState.WALK:
            self._walk_timer.start()
        else:
            self._walk_timer.stop()
        self._bus.emit(CharacterAction(action=state.value))
        logger.info("Состояние: %s (следующая смена через %d мс)", state.value, duration)
        if not self._reaction_active:
            # при реакции клип отложится до notify_animation_finished (FR-P3.5)
            self._play_state_clip()

    def _play_state_clip(self) -> None:
        state = self._fsm.state
        if self._play(clip_prefix_for(state), STATE_PRIORITY[state], True, True):
            return
        logger.warning("Анимация состояния %s недоступна — ждём без клипа (FR-P3.1)", state.value)

