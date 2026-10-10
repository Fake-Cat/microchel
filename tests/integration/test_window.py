"""Тесты окна персонажа (pytest-qt, offscreen-платформа)."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest
from PySide6.QtCore import QEvent, QPoint, QPointF, QRect, QSize, Qt
from PySide6.QtGui import QColor, QImage, QImageReader, QMouseEvent, QPainter, QPixmap
from PySide6.QtWidgets import QApplication
from pytestqt.qtbot import QtBot

from microchel.animation.queue import Priority
from microchel.common.event_bus import EventBus
from microchel.common.events import UserEvent, UserEventKind
from microchel.desktop.geometry import desktop_area
from microchel.desktop.window import PetWindow, _alpha_bbox


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

    def test_set_pet_scale_resizes_window_to_footprint(self, qtbot: QtBot) -> None:
        """Окно = фиксированный холст × pet-scale (не «кадр × масштаб клипа»)."""
        window = PetWindow()
        qtbot.addWidget(window)
        assert window.setup_animation() is True

        window.set_pet_scale(0.5)

        assert window.pet_scale == pytest.approx(0.5)
        footprint = window._footprint
        assert window.width() == max(1, int(round(footprint.width() * 0.5)))
        assert window.height() == max(1, int(round(footprint.height() * 0.5)))

    def test_set_pet_scale_keeps_bottom_center(self, qtbot: QtBot) -> None:
        """Смена масштаба держит низ-центр окна — ноги персонажа на месте."""
        window = PetWindow()
        qtbot.addWidget(window)
        assert window.setup_animation() is True
        window.move_clamped(QPoint(40, 40))
        before = window.geometry()

        window.set_pet_scale(0.5)

        after = window.geometry()
        assert after.bottom() == before.bottom()
        assert after.center().x() == before.center().x()

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


class TestClipScale:
    """Нормализация размера: масштаб клипа из clips.toml применяется в окне."""

    def test_clip_scale_applies_idle_spec_on_setup(self, qtbot: QtBot) -> None:
        """setup_animation: clip_scale = scale idle-клипа из playback-спеки."""
        window = PetWindow()
        qtbot.addWidget(window)
        assert window.setup_animation() is True

        idle = next(name for name in window.available_clip_names() if "idle" in name.casefold())
        spec_scale = window.clip_specs[idle].scale
        assert window.clip_scale == pytest.approx(spec_scale if spec_scale is not None else 1.0)

    def test_clip_scale_applies_on_animation_started_without_resize(self, qtbot: QtBot) -> None:
        """Смена клипа: масштаб применяется сразу, размер окна не меняется.

        Холст фиксирован под максимальный кадр всех клипов — окно больше не
        дёргается ни при смене клипа, ни при смене кадра (дрожание, FR-P2.6).
        """
        window = PetWindow()
        qtbot.addWidget(window)
        assert window.setup_animation() is True
        window.set_pet_scale(0.5)
        before = (window.width(), window.height())

        spec_scale = window.clip_specs["Walk/Right"].scale
        assert spec_scale is not None
        window.player.animation_started.emit("Walk/Right")

        assert window.clip_scale == pytest.approx(spec_scale)
        assert (window.width(), window.height()) == before

        # кадр другой геометрии — окно всё равно не меняется
        window._on_frame_changed(QPixmap(200, 120))
        assert (window.width(), window.height()) == before

    def test_frame_change_only_updates_without_resize(self, qtbot: QtBot) -> None:
        """Смена кадра: только update() — без resize() и repaint()."""
        window = PetWindow()
        qtbot.addWidget(window)
        assert window.setup_animation() is True
        current = window._current_frame
        assert current is not None

        with (
            patch.object(window, "repaint") as repaint,
            patch.object(window, "resize") as resize,
            patch.object(window, "update") as update,
        ):
            window._on_frame_changed(current)
            window._on_frame_changed(QPixmap(180, 240))

        repaint.assert_not_called()
        resize.assert_not_called()
        assert update.call_count == 2

    def test_clip_scale_strips_plan_suffix(self, qtbot: QtBot) -> None:
        """Имя клипа с #plan-суффиксом находит ту же спеку масштаба."""
        window = PetWindow()
        qtbot.addWidget(window)
        assert window.setup_animation() is True

        window.player.animation_started.emit("Walk/Right#12-24")

        assert window.clip_scale == pytest.approx(window.clip_specs["Walk/Right"].scale or 1.0)

    def test_unknown_clip_resets_scale_to_one(self, qtbot: QtBot) -> None:
        """Клип без спеки — масштаб нормализации снимается (1.0)."""
        window = PetWindow()
        qtbot.addWidget(window)
        assert window.setup_animation() is True
        window.player.animation_started.emit("Walk/Right")
        assert window.clip_scale != 1.0

        window.player.animation_started.emit("Unknown/Clip")

        assert window.clip_scale == 1.0

    def test_scaled_size_factor(self, qtbot: QtBot) -> None:
        """Размер отрисовки = кадр × pet-scale × clip-scale (минимум 1 px)."""
        window = PetWindow()
        qtbot.addWidget(window)
        assert window.setup_animation() is True
        window.set_pet_scale(0.5)
        window.player.animation_started.emit("Walk/Right")

        assert window._scaled_size(QSize(200, 120)) == QSize(
            max(1, int(round(200 * 0.5 * window.clip_scale))),
            max(1, int(round(120 * 0.5 * window.clip_scale))),
        )


class TestFixedCanvas:
    """Фиксированный холст: окно не дёргается, кадр якорится низ-центром (FR-P2.6)."""

    def test_window_fits_draw_size_of_every_clip(self, qtbot: QtBot) -> None:
        """Окно вмещает каждый кадр любого клипа с его масштабом — без обрезки."""
        window = PetWindow()
        qtbot.addWidget(window)
        assert window.setup_animation() is True
        assert window._clips

        for name, clip in window._clips.items():
            spec = window.clip_specs.get(name)
            scale = spec.scale if spec is not None and spec.scale is not None else 1.0
            for frame in clip.frames:
                size = QImageReader(str(frame.path)).size()
                factor = window.pet_scale * scale
                assert window.width() >= max(1, int(round(size.width() * factor))), name
                assert window.height() >= max(1, int(round(size.height() * factor))), name

    def test_paint_anchors_frame_bottom_center(self, qtbot: QtBot) -> None:
        """Кадр рисуется снизу-по-центру: над кадром фон остаётся прозрачным."""
        window = PetWindow()
        qtbot.addWidget(window)
        assert window.setup_animation() is True
        window.set_pet_scale(1.0)
        window.player.animation_started.emit("Unknown/Clip")  # clip_scale = 1.0
        solid = QPixmap(64, 64)
        solid.fill(Qt.GlobalColor.red)
        window._on_frame_changed(solid)

        image = window.grab().toImage()
        center_x = image.width() // 2
        # низ-центр: кадр прижат к нижнему краю, по горизонтали по центру
        assert image.pixelColor(center_x, image.height() - 1).alpha() > 0
        assert image.pixelColor(center_x, image.height() - 64).alpha() > 0  # верх кадра
        assert image.pixelColor(center_x, image.height() - 65).alpha() == 0  # над кадром пусто
        assert image.pixelColor(0, image.height() - 1).alpha() == 0  # слева от кадра пусто
        assert image.pixelColor(0, 0).alpha() == 0


class TestTransitionEnabled:
    """Переходный клип (MOVED CLIP): showcase отключает вставку при смене клипов."""

    def test_setup_animation_installs_transition(self, qtbot: QtBot) -> None:
        """По умолчанию смена анимации начинается с Move/Transition."""
        window = PetWindow()
        qtbot.addWidget(window)
        assert window.setup_animation() is True

        assert window.player is not None
        assert window.player.transition is not None
        assert window.player.transition.name == "Move/Transition"

    def test_disable_transition_clears_player(self, qtbot: QtBot) -> None:
        """set_transition_enabled(False) снимает переход с текущего плеера."""
        window = PetWindow()
        qtbot.addWidget(window)
        assert window.setup_animation() is True

        window.set_transition_enabled(False)

        assert window.player is not None
        assert window.player.transition is None

    def test_transition_disabled_survives_setup(self, qtbot: QtBot) -> None:
        """Смена персонажа (setup_animation) не возвращает выключенный переход."""
        window = PetWindow()
        qtbot.addWidget(window)
        window.set_transition_enabled(False)

        assert window.setup_animation() is True

        assert window.player is not None
        assert window.player.transition is None

    def test_enable_transition_restores_player(self, qtbot: QtBot) -> None:
        """Повторное включение возвращает переход текущему плееру."""
        window = PetWindow()
        qtbot.addWidget(window)
        assert window.setup_animation() is True
        window.set_transition_enabled(False)

        window.set_transition_enabled(True)

        assert window.player is not None
        assert window.player.transition is not None
        assert window.player.transition.name == "Move/Transition"


class TestFrameStats:
    """Анализатор модели: bbox и оверлей размеров (--show-frame-stats)."""

    def test_alpha_bbox_finds_model(self) -> None:
        """bbox находит прямоугольник непрозрачных пикселей."""
        img = QImage(10, 8, QImage.Format.Format_ARGB32)
        img.fill(Qt.GlobalColor.transparent)
        for x in range(2, 6):
            for y in range(3, 7):
                img.setPixelColor(x, y, QColor(255, 0, 0, 255))
        assert _alpha_bbox(img) == QRect(2, 3, 4, 4)

    def test_alpha_bbox_fully_transparent(self) -> None:
        """Пустая модель — null-прямоугольник."""
        img = QImage(6, 6, QImage.Format.Format_ARGB32)
        img.fill(Qt.GlobalColor.transparent)
        assert _alpha_bbox(img).isNull()

    def test_overlay_tracks_model_bbox(self, qtbot: QtBot) -> None:
        """Оверлей считает bbox модели текущего кадра и рисует его без ошибок."""
        window = PetWindow(frame_stats=True)
        qtbot.addWidget(window)
        assert window.setup_animation()
        clip = next(iter(window._clips.values()))
        pixmap = window.player.cache.load(clip.frames[0].path)
        window._on_frame_changed(pixmap)
        window.grab()  # форсирует paintEvent с оверлеем
        assert window._stats_bbox is not None
        assert window._stats_bbox == _alpha_bbox(pixmap.toImage())


class TestModelAnchoring:
    """Якорь отрисовки по модели: низ-центр bbox модели — в низ-центре окна."""

    def test_paint_anchors_model_not_canvas(self, qtbot: QtBot) -> None:
        """Контент смещён в канвасе — на экране модель стоит по якорю, канвас нет."""
        window = PetWindow()
        qtbot.addWidget(window)
        window.set_pet_scale(1.0)
        frame = QPixmap(64, 80)
        frame.fill(Qt.GlobalColor.transparent)
        painter = QPainter(frame)
        painter.fillRect(2, 10, 16, 40, QColor(255, 0, 0))  # модель 16×40 сдвинута влево-вверх
        painter.end()
        window._on_frame_changed(frame)

        image = window.grab().toImage()
        model_cx = image.width() // 2
        # модель: низ на земле (низ окна), центр-x в центре окна
        assert image.pixelColor(model_cx, image.height() - 1).alpha() > 0
        assert image.pixelColor(model_cx, image.height() - 40).alpha() > 0  # верх модели
        assert image.pixelColor(model_cx, image.height() - 41).alpha() == 0  # над моделью пусто
        # канвас правее модели не виден — якорь по модели, не по канвасу
        assert image.pixelColor(model_cx + 12, image.height() - 1).alpha() == 0


class TestIdleFallback:
    """Фоновая idle между анимациями: showcase выключает её (пауза без фона)."""

    def test_disable_idle_fallback_clears_player_idle(self, qtbot: QtBot) -> None:
        window = PetWindow()
        qtbot.addWidget(window)
        assert window.setup_animation() is True
        assert window.player is not None
        assert window.player._idle_clip is not None

        window.set_idle_fallback_enabled(False)

        assert window.player._idle_clip is None

    def test_idle_fallback_disabled_survives_setup(self, qtbot: QtBot) -> None:
        """Смена персонажа (setup_animation) не возвращает фоновую idle."""
        window = PetWindow()
        qtbot.addWidget(window)
        window.set_idle_fallback_enabled(False)

        assert window.setup_animation() is True

        assert window.player is not None
        assert window.player._idle_clip is None

    def test_enable_idle_fallback_restores_player(self, qtbot: QtBot) -> None:
        window = PetWindow()
        qtbot.addWidget(window)
        assert window.setup_animation() is True
        window.set_idle_fallback_enabled(False)

        window.set_idle_fallback_enabled(True)

        assert window.player is not None
        assert window.player._idle_clip is not None
        assert window.player._idle_clip.name == "Idle/Normal"
