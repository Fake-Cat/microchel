"""Тесты окна персонажа (pytest-qt, offscreen-платформа)."""

from __future__ import annotations

from pathlib import Path

import pytest
from PySide6.QtCore import QEvent, QPoint, QPointF, Qt
from PySide6.QtGui import QImage, QMouseEvent
from PySide6.QtWidgets import QApplication
from pytestqt.qtbot import QtBot

from microchel.animation.queue import Priority
from microchel.common.event_bus import EventBus
from microchel.common.events import UserEvent, UserEventKind
from microchel.desktop.geometry import desktop_area
from microchel.desktop.window import PetWindow


@pytest.fixture
def pet_window(qtbot: QtBot) -> PetWindow:
    """Окно со спрайт-фоллбэком по умолчанию (первый кадр Welcome/Greeting малинки)."""
    window = PetWindow()
    qtbot.addWidget(window)
    window.show()
    return window


@pytest.fixture
def bus() -> EventBus:
    return EventBus()


@pytest.fixture
def bus_window(qtbot: QtBot, bus: EventBus) -> PetWindow:
    """Окно, подключённое к шине (PHASE 3: клик/драг → UserEvent)."""
    window = PetWindow(bus=bus)
    qtbot.addWidget(window)
    window.show()
    return window


def _send_mouse(
    window: PetWindow,
    event_type: QEvent.Type,
    pos: QPoint,
    *,
    button: Qt.MouseButton,
    buttons: Qt.MouseButton,
) -> None:
    """Отправить мышиное событие окну с корректными глобальными координатами (FR-P3.5)."""
    event = QMouseEvent(
        event_type,
        QPointF(pos),
        QPointF(window.mapToGlobal(pos)),
        button,
        buttons,
        Qt.KeyboardModifier.NoModifier,
    )
    QApplication.sendEvent(window, event)


class TestWindowFlags:
    def test_frameless(self, pet_window: PetWindow) -> None:
        assert pet_window.windowFlags() & Qt.WindowType.FramelessWindowHint

    def test_always_on_top(self, pet_window: PetWindow) -> None:
        assert pet_window.windowFlags() & Qt.WindowType.WindowStaysOnTopHint

    def test_translucent_background(self, pet_window: PetWindow) -> None:
        assert pet_window.testAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)

    def test_sprite_loaded(self, pet_window: PetWindow) -> None:
        # спрайт-фоллбэк — первый кадр приветствия (Welcome/Greeting)
        assert not pet_window._sprite.isNull()


class TestMoveClamped:
    def test_inside_keeps_position(self, pet_window: PetWindow) -> None:
        pet_window.move_clamped(QPoint(10, 10))
        assert pet_window.pos() == QPoint(10, 10)

    def test_negative_clamped(self, pet_window: PetWindow) -> None:
        pet_window.move_clamped(QPoint(-100, -100))
        assert pet_window.pos().x() >= 0
        assert pet_window.pos().y() >= 0

    def test_far_position_clamped_to_all_screens(self, pet_window: PetWindow) -> None:
        # зажим в объединение всех экранов (мультимониторный предел)
        pet_window.move_clamped(QPoint(100_000, 100_000))
        area = desktop_area(s.availableGeometry() for s in QApplication.screens())
        assert pet_window.pos().x() <= area.x() + area.width() - pet_window.width()
        assert pet_window.pos().y() <= area.y() + area.height() - pet_window.height()


class TestContextMenu:
    def test_menu_contains_characters_and_quit(self, pet_window: PetWindow) -> None:
        menu = pet_window.build_menu()
        texts = [action.text() for action in menu.actions()]
        assert texts[-1] == "Выход"
        if "Персонаж" in texts:  # подменю есть, если персонажей больше одного
            submenu = menu.actions()[texts.index("Персонаж")].menu()
            names = [action.text() for action in submenu.actions()]
            assert pet_window.character in names
            checked = next(action for action in submenu.actions() if action.isChecked())
            assert checked.text() == pet_window.character

    def test_menu_submenu_lists_temp_characters(
        self,
        qtbot: QtBot,
        monkeypatch: pytest.MonkeyPatch,
        characters_root: Path,
    ) -> None:
        # два временных персонажа: подменю с галочкой у текущего (PHASE 4)
        monkeypatch.setattr("microchel.desktop.window.CHARACTERS_ROOT", characters_root)
        window = PetWindow()
        qtbot.addWidget(window)
        assert window.setup_animation(characters_root / "alpha") is True
        menu = window.build_menu()
        texts = [action.text() for action in menu.actions()]
        submenu = menu.actions()[texts.index("Персонаж")].menu()
        names = [action.text() for action in submenu.actions()]
        assert names == ["alpha", "beta"]
        checked = next(action for action in submenu.actions() if action.isChecked())
        assert checked.text() == "alpha"

    def test_window_visible_after_show(self, pet_window: PetWindow) -> None:
        assert pet_window.isVisible()


class TestAnimationIntegration:
    def test_setup_animation_default_is_malinka(self, pet_window: PetWindow) -> None:
        # дефолтная внешность — malinka: полный набор клипов, idle = Idle/Normal
        assert pet_window.setup_animation() is True
        names = pet_window.available_clip_names()
        assert "Welcome/Greeting" in names  # приветствие (шит WELCOME)
        assert "Walk/Left" in names  # ходьба влево = зеркало Walk/Right
        prefixes = {name.split("/")[0] for name in names}
        assert {"Idle", "Walk", "Sleep", "Sit", "Coffee", "Thinking"} <= prefixes
        assert pet_window.player is not None
        # первый кадр показан сразу; idle-фоллбэк нашёл Idle/Normal
        assert pet_window.player.frame_pixmap is not None
        assert pet_window.player.current_clip is not None
        assert pet_window.player.current_clip.name == "Idle/Normal"

    def test_setup_animation_clips_root_chooses_idle(
        self,
        pet_window: PetWindow,
        clips_root: Path,
    ) -> None:
        # временные клипы (tests/conftest.py): idle-фоллбэк ищет Idle* без учёта регистра
        assert pet_window.setup_animation(clips_root) is True
        assert pet_window.player is not None
        assert pet_window.player.current_clip is not None
        assert pet_window.player.current_clip.name.startswith("Idle/")

    def test_empty_root_falls_back_to_static_sprite(self, pet_window: PetWindow) -> None:
        assert pet_window.setup_animation(Path("/nonexistent-root")) is False
        assert pet_window.player is None

    def test_play_clip_by_prefix(self, pet_window: PetWindow, clips_root: Path) -> None:
        assert pet_window.setup_animation(clips_root) is True
        # Blink — приоритетнее idle, прерывает на границе кадра
        assert pet_window.play_clip("Blink/", priority=Priority.EVENT, loop=False) is True
        assert pet_window.player is not None
        assert pet_window.player.pending is not None or (
            pet_window.player.current_clip is not None
            and pet_window.player.current_clip.name.startswith("Blink/")
        )

    def test_play_clip_unknown_prefix_returns_false(self, pet_window: PetWindow) -> None:
        assert pet_window.setup_animation() is True
        assert pet_window.play_clip("DoesNotExist/") is False

    def test_clip_specs_loaded_for_malinka(self, pet_window: PetWindow) -> None:
        """Спека малинки прочитана из clips.toml (loop/once/mirror)."""
        assert pet_window.setup_animation() is True
        specs = pet_window.clip_specs
        assert "Walk/Direct" in specs
        assert specs["Walk/Direct"].mirror == "left"
        assert specs["Walk/Direct"].loop == (2, 10)
        assert specs["Idle/Normal"].once is True

    def test_play_clip_without_spec_file_has_empty_specs(
        self, pet_window: PetWindow, clips_root: Path
    ) -> None:
        """Во временном каталоге clips.toml нет — спека пустая, клипы работают."""
        assert pet_window.setup_animation(clips_root) is True
        assert dict(pet_window.clip_specs) == {}

    def test_play_clip_frame_indices_builds_plan_clip(
        self, pet_window: PetWindow, clips_root: Path
    ) -> None:
        """План из спеки: производный клип из кадров в заданном порядке."""
        assert pet_window.setup_animation(clips_root) is True
        assert pet_window.player is not None
        blink = next(clip for name, clip in pet_window._clips.items() if name.startswith("Blink/"))
        ordered = tuple(frame.path.name for frame in blink.frames)
        assert (
            pet_window.play_clip(
                "Blink/",
                priority=Priority.EVENT,
                restart=True,
                frame_indices=(2, 0, 2),
            )
            is True
        )
        assert pet_window.player.current_clip is not None
        planned = pet_window.player.current_clip
        assert planned.name == "Blink/Happy#plan"
        assert tuple(frame.path.name for frame in planned.frames) == (
            ordered[2],
            ordered[0],
            ordered[2],
        )

    def test_play_clip_full_range_keeps_original_clip(
        self, pet_window: PetWindow, clips_root: Path
    ) -> None:
        """План «весь клип» — не создаёт производный клип (имя для логов то же)."""
        assert pet_window.setup_animation(clips_root) is True
        assert pet_window.player is not None
        blink = next(clip for name, clip in pet_window._clips.items() if name.startswith("Blink/"))
        count = len(blink.frames)
        assert pet_window.play_clip("Blink/", restart=True, frame_indices=tuple(range(count)))
        assert pet_window.player.current_clip is not None
        assert not pet_window.player.current_clip.name.endswith("#plan")

    def test_play_clip_rejects_out_of_range_plan(
        self, pet_window: PetWindow, clips_root: Path
    ) -> None:
        assert pet_window.setup_animation(clips_root) is True
        assert pet_window.play_clip("Blink/", frame_indices=(0, 99), restart=True) is False
        assert pet_window.play_clip("Blink/", frame_indices=(), restart=True) is False

    def test_play_clip_mirror_sets_player_flag(
        self, pet_window: PetWindow, clips_root: Path
    ) -> None:
        assert pet_window.setup_animation(clips_root) is True
        assert pet_window.player is not None
        assert pet_window.play_clip("Blink/", restart=True, mirror=True) is True
        assert pet_window.player.is_mirrored is True
        assert pet_window.play_clip("Blink/", restart=True, mirror=False) is True
        assert pet_window.player.is_mirrored is False

    def test_clip_durations_returns_frame_durations(
        self, pet_window: PetWindow, clips_root: Path
    ) -> None:
        assert pet_window.setup_animation(clips_root) is True
        durations = pet_window.clip_durations("Blink/")
        assert durations is not None
        assert durations == (125, 60, 75, 60, 250)  # из имён кадров conftest
        assert pet_window.clip_durations("DoesNotExist/") is None


class TestMoveBy:
    def test_move_by_shifts_position(self, pet_window: PetWindow) -> None:
        pet_window.move_clamped(QPoint(10, 10))
        assert pet_window.move_by(5) is True
        assert pet_window.pos().x() == 15

    def test_move_by_blocked_at_edge_returns_false(self, pet_window: PetWindow) -> None:
        pet_window.move_clamped(QPoint(0, 10))
        assert pet_window.move_by(-50) is False  # позиция не изменилась → разворот (FR-P3.4)


class TestUserEventsToBus:
    """Клик/драг → события в шину (FR-P3.5)."""

    @staticmethod
    def _press(window: PetWindow, pos: QPoint) -> None:
        _send_mouse(
            window,
            QEvent.Type.MouseButtonPress,
            pos,
            button=Qt.MouseButton.LeftButton,
            buttons=Qt.MouseButton.LeftButton,
        )

    @staticmethod
    def _move(window: PetWindow, pos: QPoint) -> None:
        _send_mouse(
            window,
            QEvent.Type.MouseMove,
            pos,
            button=Qt.MouseButton.NoButton,
            buttons=Qt.MouseButton.LeftButton,
        )

    @staticmethod
    def _release(window: PetWindow, pos: QPoint) -> None:
        _send_mouse(
            window,
            QEvent.Type.MouseButtonRelease,
            pos,
            button=Qt.MouseButton.LeftButton,
            buttons=Qt.MouseButton.NoButton,
        )

    @staticmethod
    def _kinds(bus: EventBus) -> list[UserEventKind]:
        received: list[UserEventKind] = []
        bus.subscribe(UserEvent, lambda e: received.append(e.kind))
        return received

    def test_click_without_move(self, bus_window: PetWindow, bus: EventBus) -> None:
        kinds = self._kinds(bus)
        pos = QPoint(30, 30)
        self._press(bus_window, pos)
        self._release(bus_window, pos)
        assert kinds == [UserEventKind.CLICK]

    def test_drag_emits_start_then_end(self, bus_window: PetWindow, bus: EventBus) -> None:
        kinds = self._kinds(bus)
        self._press(bus_window, QPoint(30, 30))
        self._move(bus_window, QPoint(50, 50))  # смещение ≥ порога
        self._release(bus_window, QPoint(50, 50))
        assert kinds == [UserEventKind.DRAG_START, UserEventKind.DRAG_END]

    def test_jitter_below_threshold_is_click(self, bus_window: PetWindow, bus: EventBus) -> None:
        kinds = self._kinds(bus)
        self._press(bus_window, QPoint(30, 30))
        self._move(bus_window, QPoint(31, 31))  # дрожание 2 px < порога 5
        self._release(bus_window, QPoint(31, 31))
        assert kinds == [UserEventKind.CLICK]

    def test_without_bus_no_error(self, pet_window: PetWindow) -> None:
        pos = QPoint(30, 30)
        self._press(pet_window, pos)
        self._release(pet_window, pos)  # шины нет — событие просто не отправляется


class TestCharacterSwitch:
    """Смена персонажа кнопкой в меню (PHASE 4): переподключение плеера."""

    def test_available_characters_is_malinka(self, pet_window: PetWindow) -> None:
        # тестовый персонаж удалён вместе с ассетами — остаётся одна внешность
        assert pet_window.available_characters() == ["malinka"]

    def test_switch_character_replaces_player(
        self,
        qtbot: QtBot,
        monkeypatch: pytest.MonkeyPatch,
        characters_root: Path,
    ) -> None:
        monkeypatch.setattr("microchel.desktop.window.CHARACTERS_ROOT", characters_root)
        window = PetWindow()
        qtbot.addWidget(window)
        assert window.setup_animation(characters_root / "alpha") is True
        old_player = window.player
        assert window.switch_character("beta") is True
        assert window.character == "beta"
        assert window.player is not None
        assert window.player is not old_player  # новый плеер
        assert old_player is not None and not old_player.is_playing  # старый остановлен
        assert window.available_clip_names() == ["Idle/Happy"]  # клипы beta

    def test_switch_unknown_character_keeps_current(
        self,
        qtbot: QtBot,
        monkeypatch: pytest.MonkeyPatch,
        characters_root: Path,
    ) -> None:
        monkeypatch.setattr("microchel.desktop.window.CHARACTERS_ROOT", characters_root)
        window = PetWindow()
        qtbot.addWidget(window)
        assert window.setup_animation(characters_root / "alpha") is True
        current = window.player
        assert window.switch_character("does-not-exist") is False
        assert window.player is current
        assert window.character == "alpha"


class TestScaleFadeSpeed:
    """Масштаб персонажа и скорость (PHASE 4); кадры сменяются без кроссфейда."""

    def test_default_scale_and_speed(self, pet_window: PetWindow) -> None:
        assert pet_window.pet_scale == pytest.approx(0.65)
        assert pet_window.animation_speed == 1.0

    def test_set_pet_scale_resizes_window(self, qtbot: QtBot) -> None:
        window = PetWindow()
        qtbot.addWidget(window)
        assert window.setup_animation() is True
        frame = window._current_frame
        assert frame is not None

        window.set_pet_scale(0.5)

        assert window.pet_scale == pytest.approx(0.5)
        assert window.width() == max(1, int(round(frame.width() * 0.5)))
        assert window.height() == max(1, int(round(frame.height() * 0.5)))

    def test_invalid_pet_scale_rejected(self, pet_window: PetWindow) -> None:
        pet_window.set_pet_scale(0)
        assert pet_window.pet_scale == pytest.approx(0.65)  # дефолт не тронут

    def test_frame_change_swaps_frame_without_fade(self, qtbot: QtBot) -> None:
        """Смена кадра сразу показывает новый кадр — без кроссфейда и полупрозрачности."""
        window = PetWindow()
        qtbot.addWidget(window)
        assert window.setup_animation() is True
        first = window._current_frame
        assert first is not None

        assert window.play_clip("Walk/", restart=True) is True
        second = window._current_frame
        assert second is not None

        # пиксели нового кадра непрозрачны сразу после смены (нет opacity-смешивания)
        img = second.toImage()
        assert not img.isNull()
        assert img.format() != QImage.Format.Format_Invalid

    def test_set_animation_speed_propagates_to_player(self, qtbot: QtBot) -> None:
        window = PetWindow()
        qtbot.addWidget(window)
        assert window.setup_animation() is True

        window.set_animation_speed(0.5)

        assert window.animation_speed == 0.5
        assert window.play_clip("Talk/", restart=True) is True
        assert window.player is not None
        assert window.player.speed == 0.5

    def test_invalid_animation_speed_rejected(self, pet_window: PetWindow) -> None:
        pet_window.set_animation_speed(-1)
        assert pet_window.animation_speed == 1.0  # дефолт не тронут
