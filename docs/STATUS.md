# docs/STATUS.md — текущее состояние

**Дата последнего обновления:** 2026-10-08 (вечер)
**Текущий этап:** **PHASE 3 — Character Behavior — шаг 10 (ручные сценарии) ВЫПОЛНЕН**; остался шаг 11 — коммит по команде пользователя

## Где мы находимся (для продолжения в новом сеансе)

1. PHASE 0 ✅, PHASE 1 ✅, PHASE 2 ✅. **PHASE 3: шаги 1–10 выполнены** (план `docs/PHASE3_PLAN.md`): события/шина, states/config/fsm/controller, `config/behavior.toml`, генератор клипов, интеграция окно+main, флаги `--demo` / `--demo-events` / `--showcase`; тесты **167 passed, ruff чисто**.
2. **Сценарии P3-1…P3-7 — все подтверждены** (TESTING.md, 2026-10-08): автономность ≥10 мин, ходьба с разворотом у края (лог `разворот → -1`, позиция 5500→5563→5447), клик/драг глазами пользователя, 13+ событий `--demo-events` (интервалы 47–89 с), ночь (сон 14,4 мин из прогонного окна), RSS 104,5→105,5 МБ.
3. **Найден и исправлен баг:** `start_behavior` вызывал `load_behavior_config()` без пути → `path=None` → всегда дефолты, `config/behavior.toml` в приложении **не читался вообще** (тесты были зелёные, т.к. файл зеркалит дефолты). Фикс: `load_behavior_config(DEFAULT_CONFIG_PATH)` + регресс-тест `test_start_behavior_loads_config_file`.
4. **Ключевые решения PHASE 3:** FSM чистый (без Qt), случайность через seeded `random.Random`, ночь — через `hour`-колбэк; `night.sleep_weight = 300` (сон ~78% ночью, выбор пользователя); state-клипы `loop=True` + `restart=True` (правка плеера); реакция на клик REACTION с возвратом через `animation_finished`; разворот у края — `EdgeWalker` (чистый, юнит-тесты); `available` FSM = состояния с клипами (нет клипа → пропуск, FR-P3.1).
5. **UX-наблюдение:** системные события поверх сна (blink ~570 мс стоячей позой) выглядят как «резкое пробуждение на секунду» — сон FSM не прерывается. В TESTING.md «Известные ошибки» №3 → PHASE 4 (лежачий blink/пауза реакций в сне).
6. **Git:** коммиты `9302f3f`, `987c3a8`, `030d183`, `3051dac`, `bbe51e8`; все изменения PHASE 3 **не закоммичены** (коммит — по команде).
7. **Следующее действие:** коммит PHASE 3 по команде пользователя (документация обновлена).

## Ключевые решения / где что лежит

- Состояния/маппинг: `character/states.py` (`STATE_CLIP_PREFIX`, `STATE_PRIORITY`, `TRANSIENT_STATES`).
- Конфиг: `config/behavior.toml` + `character/config.py::load_behavior_config` (битые значения → дефолт + лог); **путь передаёт `start_behavior`** (`DEFAULT_CONFIG_PATH`) — вызов без пути возвращает только дефолты (баг, исправлен 2026-10-08).
- FSM: `character/fsm.py` (`BehaviorFSM`, `is_night`); выбор — `rng.choices` по весам, ночью вес SLEEP ×(ночной бонус).
- Контроллер: `character/controller.py` (`CharacterController`, `EdgeWalker`); 2 QTimer (состояние + шаг ходьбы).
- Шина/события: `common/event_bus.py`, `common/events.py`; клик/драг порог 5 px — `desktop/window.py` (`DRAG_THRESHOLD_PX`).
- Сборка: `desktop/main.py::start_behavior/start_demo_events/states_with_clips`.
- Плеер (правки PHASE 3): `restart=True` — немедленная замена клипа; `_start_next` не перетирает клип, запущенный слушателем `animation_finished`.
- Демо-ассеты: `scripts/make_test_animations.py` → `assets/characters/test/` — **7 клипов** (Idle/Blink/Walk/Sleep/Sit/Coffee/Thinking, свой материал).

## Последняя завершённая задача

Шаг 10 PHASE 3 — ручные сценарии **P3-1…P3-7 все OK (2026-10-08, TESTING.md)** + исправлен баг загрузки `config/behavior.toml` (вызов `load_behavior_config()` без пути → файл в приложении не читался) с регресс-тестом; **167 passed / ruff чисто**.

## Что реализовано (PHASE 3, доп. к PHASE 0–2)

- `src/microchel/common/events.py`, `src/microchel/common/event_bus.py` — типы событий и синхронная шина.
- `src/microchel/character/` — `states.py`, `config.py`, `fsm.py`, `controller.py`; `config/behavior.toml`.
- `desktop/window.py` — клик/драг → `UserEvent` в шину (порог 5 px), `move_by(dx)` для ходьбы.
- `desktop/main.py` — сборка controller, флаги `--demo` (взаимоисключен с FSM) и `--demo-events` (45–90 с).
- Тесты: `tests/unit/test_{events,states,behavior_config,fsm,controller}.py`, `tests/integration/test_{character_controller,start_behavior,demo_events}.py` + расширены `test_player/test_window/test_main`.

## Что работает / что проверено

| Проверка | Результат |
|---|---|
| `pytest` | **167 passed** (вкл. регресс-тест загрузки конфига) |
| `ruff check .` | **All checks passed** |
| Генерация ассетов | 7 клипов загружаются (`discover_clip_dirs`) |
| Smoke offscreen 20 с | старт без ошибок, «Поведение подключено», все 6 состояний |
| Smoke offscreen 90 с | переходы `idle → walk → idle` в логе, клипы Idle→Walk→Idle, 0 ошибок |
| Ручные сценарии P3-1…P3-7 | **все OK 2026-10-08** (TESTING.md: ≥10 мин, разворот у края, RSS, ночь, события) |
| Загрузка `behavior.toml` | фикс 2026-10-08: `start_behavior` → `load_behavior_config(DEFAULT_CONFIG_PATH)`; до фикса файл не читался в приложении |
| `--demo-events` живой | 13+ событий, интервалы 47–89 с (в границах 45–90) |

## Что сломано / что не проверено

- **Визуальная верификация скриншотами невозможна** на dev-стенде: grim/scrot отсутствуют, ffmpeg x11grab под Wayland даёт чёрный кадр — проверка глазами пользователя (зафиксировано в TESTING.md).
- Замечание о плавности движения → PHASE 4; «blink поверх сна» (стоячая поза выглядит как резкое пробуждение) → PHASE 4 (TESTING.md, Известные ошибки №3).
- Ubuntu X11 и RPi — не проверялись (нет сред).

## Известные ограничения и риски

1–4 — как в PHASE 2 (Wayland/xcb, RPi, MIT, лицензии VPet) + замечание о плавности движения → PHASE 4.
5. **Приоритет REACTION vs событие во время клика:** `SystemEvent` во время играющей реакции уходит в no-op (blink уже играет) — визуально корректно, задокументировано в `controller._on_system_event`.

## Следующее конкретное действие

**Коммит PHASE 3** (шаг 11) — по команде пользователя: код + фикс загрузки конфига + тесты (167) + документация.

## Команды для запуска и тестирования

```bash
cd /home/fake-cat/projects/microchel
source .venv/bin/activate
pytest                                  # 167 passed
ruff check .                            # чисто
python -m microchel.desktop.main        # автономное поведение (под Wayland сам выберет xcb)
python -m microchel.desktop.main --demo # PHASE 2 демо (FSM отключён)
python -m microchel.desktop.main --demo-events  # + синтетические события 45–90 с
python -m microchel.desktop.main --showcase     # все клипы по 10 с подряд (ручной показ)
QT_QPA_PLATFORM=offscreen python scripts/make_test_animations.py   # перегенерация клипов
```

## Блокирующие проблемы

Нет.
