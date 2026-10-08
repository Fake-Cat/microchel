# docs/STATUS.md — текущее состояние

**Дата последнего обновления:** 2026-10-08
**Текущий этап:** **PHASE 2 — ЗАКРЫТ (2026-10-08, с замечанием по плавности → PHASE 4)**; следующий — PHASE 3 (Character Behavior), ждём команды

## Где мы находимся (для продолжения в новом сеансе)

1. PHASE 0 ✅, PHASE 1 ✅, **PHASE 2 ✅ закрыт**: анимационный движок (`animation/`: frames/cache/queue/player), интеграция в окно, `--demo`; **pytest 77 passed, ruff чист**; сценарии P2 подтверждены пользователем; RSS стабилен (104356 kB / 6 мин).
2. **Ключевые решения PHASE 2:** формат кадров `_NNN_DDD.png` (ADR-005); длительности — из имён файлов; приоритеты IDLE<BEHAVIOR<EVENT<REACTION; LRU-кэш 64 МБ; прерывание на границе кадра, возврат к idle.
3. Окно работает с анимациями: `python -m microchel.desktop.main [--demo]`.
4. **Открытое замечание:** неплавность вертикального движения (idle/walk) — улучшить в PHASE 4 (TESTING, Известные ошибки №1).
5. **Git:** коммиты `9302f3f` (bootstrap), `987c3a8` (PHASE 1), `030d183` (docs), `3051dac` (PHASE 2). Лицензия MIT.
6. **Следующее действие:** по команде — PHASE 3 (Character Behavior: FSM idle/walk/sleep/sit/coffee/thinking, события, автономный выбор).

## Ключевые решения / где что лежит

- Плеер: `src/microchel/animation/player.py`; формат кадров — ADR-005 (`_NNN_DDD.png`).
- Приоритеты: `animation/queue.py::Priority` (reaction > event > behavior > idle).
- Кэш: `animation/cache.py::FrameCache` — LRU, дефолт 64 МБ, без Qt (загрузчик-колбэк).
- Демо-ассеты: `scripts/make_test_animations.py` → `assets/characters/test/{Idle,Blink,Walk}/` (свой материал, ADR-004 не задет).

## Последняя завершённая задача

PHASE 2 (Animation Engine): пакет `animation/` — парсер кадров `_NNN_DDD.png` (ADR-005), LRU-кэш 64 МБ, приоритетная очередь (idle<behavior<event<reaction), плеер с таймингами из имён файлов; интеграция в `PetWindow` (показ кадров, автоподстройка размера), флаг `--demo`; 77 тестов, ruff чисто; сценарии P2 подтверждены пользователем.

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
| `pytest` | **77 passed** |
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

**PHASE 2 закрыт (коммит `3051dac`).** Дальше по очереди:
1. Спросить команду на **PHASE 3 (Character Behavior)**: FSM idle/walk/sleep/sit/coffee/thinking, события пользователя/системы, автономный выбор (критерий ≥10 мин естественного поведения).
2. Опционально: взять замечание по плавности движения (TESTING «Известные ошибки» №1) сейчас или оставить до PHASE 4.

## Команды для запуска и тестирования

```bash
cd /home/fake-cat/projects/microchel
source .venv/bin/activate
pytest                                  # 77 passed
ruff check .                            # чисто
python -m microchel.desktop.main        # запуск питомца (под Wayland сам выберет xcb)
QT_QPA_PLATFORM=offscreen python scripts/make_test_sprite.py   # перегенерация спрайта
```

## Блокирующие проблемы

Нет. Ожидается результат ручной проверки окна.
