"""FSM поведения (PHASE 3, FR-P3.1, FR-P3.2, FR-P3.5).

Чистая логика без Qt: состояния, тайминги, весовой автономный выбор,
обработка событий пользователя. Случайность — через внедрённый
`random.Random` (seed в тестах → детерминизм), время суток — через
внедрённый `hour`-колбэк (по умолчанию — системные часы).
"""

from __future__ import annotations

import logging
import random
from collections.abc import Callable, Iterable

from microchel.character.config import BehaviorConfig
from microchel.character.states import TRANSIENT_STATES, CharacterState
from microchel.common.events import UserEventKind

logger = logging.getLogger(__name__)


def is_night(hour: int, from_hour: int, to_hour: int) -> bool:
    """True, если час попадает в ночной интервал (с поддержкой перехода через полночь)."""
    if from_hour == to_hour:
        return False
    if from_hour < to_hour:
        return from_hour <= hour < to_hour
    return hour >= from_hour or hour < to_hour


class BehaviorFSM:
    """Конечный автомат: IDLE ↔ одноразовые состояния (walk/sit/coffee/thinking/sleep)."""

    def __init__(
        self,
        config: BehaviorConfig,
        *,
        rng: random.Random | None = None,
        available: Iterable[CharacterState] | None = None,
        hour: Callable[[], int] | None = None,
    ) -> None:
        self._config = config
        self._rng = rng if rng is not None else random.Random()
        self._hour = hour if hour is not None else _system_hour
        states = frozenset(available) if available is not None else frozenset(CharacterState)
        # IDLE всегда доступен: без него FSM некуда переходить
        self._available: frozenset[CharacterState] = states | {CharacterState.IDLE}
        self._state = CharacterState.IDLE

    @property
    def state(self) -> CharacterState:
        return self._state

    @property
    def available(self) -> frozenset[CharacterState]:
        return self._available

    @property
    def config(self) -> BehaviorConfig:
        return self._config

    def state_duration_ms(self) -> int:
        """Длительность пребывания в текущем состоянии (случайная из пары min/max)."""
        low, high = self._config.duration_ms(self._state)
        if low >= high:
            return low
        return self._rng.randint(low, high)

    def on_timeout(self) -> CharacterState:
        """Текущее состояние истекло → перейти в следующее, вернуть его."""
        if self._state is not CharacterState.IDLE:
            # одноразовое состояние всегда завершается возвратом в idle (FR-P3.1)
            previous = self._state
            self._state = CharacterState.IDLE
            logger.debug("FSM: %s → idle (длительность истекла)", previous.value)
            return self._state
        self._state = self._choose_next()
        logger.info("FSM: idle → %s", self._state.value)
        return self._state

    def on_user_event(self, kind: UserEventKind) -> CharacterState | None:
        """Реакция на событие пользователя; None — состояние не изменилось.

        DRAG_START прерывает ходьбу (FR-P3.5): пит «в руках у пользователя».
        CLICK обрабатывает controller (поверхная реакция, состояние не меняется).
        """
        if kind is UserEventKind.DRAG_START and self._state is CharacterState.WALK:
            self._state = CharacterState.IDLE
            logger.info("FSM: walk прерван драгом → idle")
            return self._state
        return None

    def force(self, state: CharacterState) -> None:
        """Перевести в состояние вручную (тесты, восстановление после сбоев)."""
        self._state = state

    def _choose_next(self) -> CharacterState:
        """Весовой выбор следующего состояния из доступных (FR-P3.2)."""
        candidates = sorted(
            (state for state in TRANSIENT_STATES if state in self._available),
            key=str,
        )
        if not candidates:
            return CharacterState.IDLE
        night = is_night(self._hour(), self._config.night_from, self._config.night_to)
        weights = [self._weight_for(state, night) for state in candidates]
        if sum(weights) <= 0:
            logger.warning("FSM: все веса равны 0 — остаёмся в idle")
            return CharacterState.IDLE
        return self._rng.choices(candidates, weights=weights, k=1)[0]

    def _weight_for(self, state: CharacterState, night: bool) -> int:
        weight = self._config.weight(state)
        if night and state is CharacterState.SLEEP:
            weight += self._config.night_sleep_weight
        return weight


def _system_hour() -> int:
    from datetime import datetime

    return datetime.now().hour
