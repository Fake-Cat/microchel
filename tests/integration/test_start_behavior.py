"""Сборка поведения целиком: окно + плеер + шина + контроллер (PHASE 3, FR-P3.8).

Отличие от test_character_controller: здесь настоящий плеер и настоящие клипы
из tests/conftest.py (generate_clips → временный каталог), а не заглушки play/move.
"""

from __future__ import annotations

import logging
from pathlib import Path

import pytest
from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap
from pytestqt.qtbot import QtBot

from microchel.character.config import DEFAULT_CONFIG_PATH, BehaviorConfig
from microchel.character.controller import CharacterController
from microchel.common.event_bus import EventBus
from microchel.common.events import CharacterAction, UserEvent, UserEventKind
from microchel.desktop.main import start_behavior
from microchel.desktop.window import PetWindow

Wired = tuple[QtBot, PetWindow, EventBus, CharacterController, list[str]]


@pytest.fixture
def wired(qtbot: QtBot, clips_root: Path) -> Wired:
    bus = EventBus()
    window = PetWindow(bus=bus)
    qtbot.addWidget(window)
    assert window.setup_animation(clips_root)
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
        # временные клипы (conftest) содержают все 7 префиксов → FSM со всеми
        # состояниями (IDLE + 5 одноразовых); временные клипы (conftest) полные
        assert len(controller.fsm.available) == 6
        prefixes = {name.split("/")[0] for name in window.available_clip_names()}
        assert {"Idle", "Walk", "Sleep", "Sit", "Coffee", "Thinking", "Blink"} <= prefixes

    def test_start_behavior_loads_config_file(
        self,
        qtbot: QtBot,
        monkeypatch: pytest.MonkeyPatch,
        clips_root: Path,
    ) -> None:
        # регресс (23.10.2026): start_behavior вызывал load_behavior_config() без
        # пути → path=None → всегда дефолты, а config/behavior.toml не читался
        bus = EventBus()
        window = PetWindow(bus=bus)
        qtbot.addWidget(window)
        assert window.setup_animation(clips_root)
        captured: list[Path | None] = []

        def spy(path: Path | None) -> BehaviorConfig:
            captured.append(path)
            return BehaviorConfig()

        monkeypatch.setattr("microchel.desktop.main.load_behavior_config", spy)
        controller = start_behavior(window, bus)
        assert controller is not None
        assert captured == [DEFAULT_CONFIG_PATH]


def test_welcome_only_behavior_not_started(
    qtbot: QtBot,
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Персонаж только с приветствием (без клипов состояний) → поведение не включается.

    Одна info-строка вместо предупреждения по каждому состоянию (NF-P3.5,
    решение 2026-10-10). malinka теперь полная, поэтому welcome-only
    персонаж собирается во временном каталоге из двух кадров.
    """
    clip_dir = tmp_path / "Welcome" / "Greeting" / "1"
    clip_dir.mkdir(parents=True)
    for index in range(2):
        pixmap = QPixmap(64, 64)
        pixmap.fill(Qt.GlobalColor.transparent)
        assert pixmap.save(str(clip_dir / f"_{index:03d}_100.png"), "PNG")
    bus = EventBus()
    window = PetWindow(bus=bus)
    qtbot.addWidget(window)
    assert window.setup_animation(tmp_path) is True  # только приветствие
    with caplog.at_level(logging.INFO, logger="microchel.desktop.main"):
        assert start_behavior(window, bus) is None
    records = [record for record in caplog.records if record.name == "microchel.desktop.main"]
    assert len(records) == 1  # одна строка вместо шести предупреждений
    assert records[0].levelname == "INFO"
    assert not [record for record in caplog.records if record.levelno >= logging.WARNING]
