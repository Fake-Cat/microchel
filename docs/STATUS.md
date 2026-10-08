# docs/STATUS.md — текущее состояние

**Дата последнего обновления:** 2026-10-08
**Текущий этап:** **PHASE 1 — ЗАКРЫТ (2026-10-08)**; следующий — PHASE 2 (Animation Engine), ждём команды

## Где мы находимся (для продолжения в новом сеансе)

1. PHASE 0 ✅, **PHASE 1 ✅ закрыт**: все сценарии TESTING.md 1–6 OK, pytest **31 passed**, ruff чист.
2. **Ключевые решения PHASE 1:** под Wayland авто-запуск через XWayland (`select_qt_platform()` → xcb, ADR-002); системная зависимость `libxcb-cursor0`; мультимониторный зажим `desktop_area()` (объединение всех экранов — пит ездит по 3 мониторам).
3. Окно запускается: `python -m microchel.desktop.main` (xcb выбирается сам).
4. **Открытый вопрос пользователю:** Git-коммит (всё ещё untracked; лицензия MIT выбрана 2026-10-08).
5. **Следующее действие:** по команде — PHASE 2 (Animation Engine, формат `_NNN_DDD.png`).

## Последняя завершённая задача

Минимальный GUI-прототип: прозрачное frameless-окно 160×160 со спрайтом, drag ЛКМ с зажимом координат, контекстное меню «Выход», always-on-top флаг, логирование платформы Qt.

## Что реализовано

- `src/microchel/common/logging_config.py` — логирование (MICROCHEL_LOG_LEVEL).
- `src/microchel/desktop/geometry.py` — чистые `clamp_axis`/`clamp_to_screen`.
- `src/microchel/desktop/window.py` — `PetWindow`: frameless + WA_TranslucentBackground + WindowStaysOnTopHint, отрисовка спрайта, drag, `move_clamped`, меню «Выход».
- `src/microchel/desktop/main.py` — точка входа `python -m microchel.desktop.main`.
- `scripts/make_test_sprite.py` → `assets/characters/test/test_idle.png` (160×160 RGBA, свой материал).
- Тесты: `tests/unit/test_geometry.py`, `tests/integration/test_window.py`, `tests/unit/test_smoke.py`.

## Что работает / что проверено

| Проверка | Результат |
|---|---|
| ОС / Python / Git | Ubuntu 26.04.1 x86-64, Python 3.14.4, Git 2.53.0 |
| Сессия | **Wayland** (XDG_SESSION_TYPE=wayland), XWayland :0 доступен |
| `.venv` | PySide6 **6.12.0 / Qt 6.12.0**, pytest 9.1.1, pytest-qt 4.5.0, ruff 0.16.10 |
| `pytest` | **31 passed** |
| `ruff check .` | **All checks passed** |
| Спрайт | PNG 160×160 RGBA сгенерирован |
| Нативный запуск | wayland: драг невозможен → **xcb: всё OK** (авто-выбор в main.py) |
| Ручные сценарии 1–6 | **все OK 2026-10-08** |
| Мультимонитор (3 экрана) | **OK** — драг между мониторами, зажим в общий bbox |

## Что сломано / что не проверено

- Под нативным wayland драг невозможен в принципе (ADR-002) — обход через авто-xcb (проверено).
- Не проверено: X11-сессия (RPi), поведение при обновлении Qt/Ubuntu (XWayland).

## Известные ограничения и риски

1. **Wayland закрыт через xcb** (ADR-002, уточнён): авто-выбор в `main.py`, нужен `libxcb-cursor0`. Остаточный риск: XWayland — медленно развивающийся путь; перепроверить при обновлениях Qt/Ubuntu.
2. **Raspberry Pi не пришла** — бюджеты памяти (4 GB) держим в голове, профилирование с PHASE 2.
3. Лицензия собственного кода — **MIT** (LICENSE создан 2026-10-08, по выбору пользователя).
4. Анимации VPet — не-коммерческие условия (RESEARCH_VPET.md).

## Следующее конкретное действие

**PHASE 1 закрыт.** Дальше по очереди:
1. Спросить пользователя: Git-коммит? Лицензия (MIT/Apache-2.0)?
2. По команде — PHASE 2 (Animation Engine, формат `_NNN_DDD.png`, плеер, кэш).

## Команды для запуска и тестирования

```bash
cd /home/fake-cat/projects/microchel
source .venv/bin/activate
pytest                                  # 26 passed
ruff check .                            # чисто
python -m microchel.desktop.main        # запуск питомца (под Wayland сам выберет xcb)
QT_QPA_PLATFORM=offscreen python scripts/make_test_sprite.py   # перегенерация спрайта
```

## Блокирующие проблемы

Нет. Ожидается результат ручной проверки окна.
