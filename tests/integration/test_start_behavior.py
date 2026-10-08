"""Сборка поведения целиком: окно + плеер + шина + контроллер (PHASE 3, FR-P3.8).

Отличие от test_character_controller: здесь настоящий плеер и настоящие клипы
из assets/characters/test, а не заглушки play/move.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from pytestqt.qtbot import QtBot

from microchel.character.config import DEFAULT_CONFIG_PATH, BehaviorConfig
from microchel.character.controller import CharacterController
from microchel.common.event_bus import EventBus
from microchel.common.events import CharacterAction, UserEvent, UserEventKind
from microchel.desktop.main import start_behavior
from microchel.desktop.window import PetWindow

ASSETS_ROOT = Path(__file__).resolve().parents[2] / "assets" / "characters" / "test"

Wired = tuple[QtBot, PetWindow, EventBus, CharacterController, list[str]]


@pytest.fixture
def wired(qtbot: QtBot) -> Wired:
    bus = EventBus()
    window = PetWindow(bus=bus)
    qtbot.addWidget(window)
    assert window.setup_animation(ASSETS_ROOT)
    window.show()
    actions: list[str] = []
    bus.subscribe(CharacterAction, lambda e: actions.append(e.action))
    controller = start_behavior(window, bus)
    assert controller is not None
    assert controller.started
    return qtbot, window, bus, controller, actions


class TestBehaviorWiring:
    def test_start_shows_idle_clip(self, wired: Wired) -> None:
        _qtbot, window, _bus, controller, actions = wired
        assert actions[0] == "idle"
        assert window.player is not None
        assert window.player.current_clip is not None
        assert window.player.current_clip.name.startswith("Idle/")
        assert controller.fsm.state.value == "idle"

    def test_click_reaction_with_real_player(self, wired: Wired) -> None:
        qtbot, window, bus, controller, _actions = wired
        assert window.player is not None
        bus.emit(UserEvent(UserEventKind.CLICK))
        assert controller.reaction_active
        # прерывание на границе кадра idle → Blink играет
        qtbot.waitUntil(
            lambda: window.player is not None
            and window.player.current_clip is not None
            and window.player.current_clip.name.startswith("Blink/"),
            timeout=3000,
        )
        # реакция доигрывает сама (реальный таймер) → состояние возобновляется
        qtbot.waitUntil(lambda: not controller.reaction_active, timeout=3000)
        qtbot.waitUntil(
            lambda: window.player is not None
            and window.player.current_clip is not None
            and window.player.current_clip.name.startswith("Idle/"),
            timeout=3000,
        )

    def test_all_states_have_clips_in_assets(self, wired: Wired) -> None:
        _qtbot, window, _bus, controller, _actions = wired
        # в assets/ все 7 клипов → FSM со всеми состояниями (IDLE + 5 одноразовых)
        assert len(controller.fsm.available) == 6
        prefixes = {name.split("/")[0] for name in window.available_clip_names()}
        assert {"Idle", "Walk", "Sleep", "Sit", "Coffee", "Thinking", "Blink"} <= prefixes

    def test_start_behavior_loads_config_file(
        self, qtbot: QtBot, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # регресс (23.10.2026): start_behavior вызывал load_behavior_config() без
        # пути → path=None → всегда дефолты, а config/behavior.toml не читался
        bus = EventBus()
        window = PetWindow(bus=bus)
        qtbot.addWidget(window)
        assert window.setup_animation(ASSETS_ROOT)
        captured: list[Path | None] = []

        def spy(path: Path | None) -> BehaviorConfig:
            captured.append(path)
            return BehaviorConfig()

        monkeypatch.setattr("microchel.desktop.main.load_behavior_config", spy)
        controller = start_behavior(window, bus)
        assert controller is not None
        assert captured == [DEFAULT_CONFIG_PATH]
