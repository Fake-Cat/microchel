# docs/CHANGELOG.md — изменения проекта

Формат: по датам, новые сверху.

## 2026-10-08 — PHASE 3: результаты P3-1…P3-7 и фикс загрузки конфига

### Исправлено

- `desktop/main.py::start_behavior` — вызывал `load_behavior_config()` **без пути** → `path=None` → всегда дефолты: `config/behavior.toml` в приложении не читался (тесты были зелёные, т.к. файл зеркалит дефолты). Теперь передаётся `DEFAULT_CONFIG_PATH`; регресс-тест `test_start_behavior_loads_config_file`.

### Добавлено

- Результаты ручных сценарий **P3-1…P3-7 — все OK (2026-10-08)** в TESTING.md (автономность ≥10 мин, ходьба с разворотом у края, RSS 104,5→105,5 МБ, ночь, события 47–89 с, клик/драг).
- Референс внешности и фонов: `docs/Микрочел_ питомец на Raspberry Pi.png` (собственный материал, подтверждено пользователем 2026-10-08). Идея «фон-задник за персонажем для отдельных состояний/эмоций/задач» → ROADMAP, PHASE 4.
- TESTING.md, Известные ошибки №3 — «blink поверх сна» как UX-замечание → PHASE 4.
- Тестов: **167 passed** (было 162), ruff чисто.

---

## 2026-10-08 — PHASE 3 (Character Behavior, шаги 1–9)

### Добавлено

- `docs/PHASE3_PLAN.md` — требования FR-P3.1…NF-P3.5 и план шагов 1–11.
- `src/microchel/common/events.py` — `UserEvent` (CLICK/DRAG_START/DRAG_END), `SystemEvent` (SYNTHETIC), `CharacterAction`; `src/microchel/common/event_bus.py` — синхронная шина.
- `src/microchel/character/`: `states.py` (enum + маппинг состояние→клип/приоритет), `config.py` + `config/behavior.toml` (тайминги, веса, ночь, шаг ходьбы; битые значения → дефолт), `fsm.py` (`BehaviorFSM` — взвешенный автономный выбор, seeded Random, ночь, события), `controller.py` (`CharacterController` — 2 QTimer, шина, play/move-колбэки; `EdgeWalker` — разворот у края).
- `scripts/make_test_animations.py` — клипы Sleep/Sit/Coffee/Thinking (позы, Z, кружка, пузырьки; итого 7 клипов).
- `--demo-events` — синтетические системные события раз в 45–90 с (заглушка источника до PHASE 7).
- `--showcase` — последовательный показ всех клипов по 10 с (Idle → Blink → Coffee → Sit → Sleep → Thinking → Walk, цикл повторяется; взаимоисключен с `--demo`).
- Тесты: `tests/unit/test_{events,states,behavior_config,fsm,controller}.py`, `tests/integration/test_{character_controller,start_behavior,demo_events}.py` — **162 passed**.

### Изменено

- `desktop/window.py` — `bus` в конструкторе; клик/драг → `UserEvent` (порог 5 px); `move_by(dx)` (возврат «двигнулось») для ходьбы.
- `desktop/main.py` — сборка поведения (`start_behavior`, `states_with_clips`: нет клипа → состояние исключено с предупреждением); `--demo` отключает FSM (FR-P3.8).
- `animation/player.py` — `restart=True` немеденно заменяет текущий клип (в т.ч. другой — переходы looping-состояний); `_start_next` не перетирает клип, запущенный слушателем `animation_finished`.
- `desktop/window.py::play_clip` — параметр `restart`.
- `docs/ARCHITECTURE.md` — «Форматы событий» и «Модель состояний» зафиксированы (уточнены в PHASE 3).

---

## 2026-10-08 — PHASE 2 (Animation Engine)

### Добавлено

- `docs/PHASE2_PLAN.md` — требования и план PHASE 2.
- `src/microchel/animation/`: `frames.py` (парсер `_NNN_DDD.png`, load_clip, discover), `cache.py` (LRU-кэш по байтам), `queue.py` (приоритеты IDLE/BEHAVIOR/EVENT/REACTION), `player.py` (плеер: тайминги из имён, loop, прерывание на границе кадра, возврат к idle).
- `scripts/make_test_animations.py` — генератор демо-клипов (idle/blink/walk, 17 кадров).
- `assets/characters/test/{Idle,Blink,Walk}/…` — сгенерированные тестовые кадры.
- `tests/unit/test_frames.py`, `tests/unit/test_cache.py`, `tests/unit/test_queue.py`, `tests/integration/test_player.py` (итого 77 passed).

### Изменено

- `desktop/window.py` — `setup_animation()`, показ кадров плеера, автоподстройка размера с сохранением центра, `play_clip()`.
- `desktop/main.py` — флаг `--demo` (случайные анимации каждые 4 с).

---

## 2026-10-08 — PHASE 1 (bootstrap + Minimal Desktop Pet)

### Добавлено

- `LICENSE` — **MIT** (выбрано пользователем 2026-10-08), `license = { text = "MIT" }` в pyproject.toml.
- `src/microchel/common/logging_config.py`, `src/microchel/desktop/{main,window,geometry}.py`.
- `src/microchel/desktop/main.py::select_qt_platform()` — авто-запуск через xcb под Wayland (ADR-002).
- `src/microchel/desktop/geometry.py::desktop_area()` — мультимониторный зажим (объединение всех экранов).
- `scripts/make_test_sprite.py`, `assets/characters/test/test_idle.png` (160×160 RGBA).
- Тесты: `tests/unit/test_geometry.py`, `tests/unit/test_main.py`, `tests/integration/test_window.py` (31 passed всего).
- Вся документация PHASE 0: AGENTS.md, README.md, docs/*, ADR-001…005, pyproject.toml, .gitignore, .env.example.

### Изменено

- `docs/decisions/ADR-002-windowing.md` — уточнён по факту: результаты проверки Wayland/XWayland.
- `docs/TESTING.md` — сценарии 1–6 **все OK (2026-10-08)** + мультимонитор.
- Git: созданы коммиты `9302f3f` (bootstrap) и `987c3a8` (PHASE 1).

### Удалено

— ничего.

---

## 2026-10-08 — PHASE 0 (bootstrap)

### Добавлено

- Структура репозитория: `src/microchel/*` (9 пакетов), `assets/`, `config/`, `tests/`, `scripts/`, `packaging/`, `docs/decisions/`.
- `AGENTS.md`, `README.md`, `pyproject.toml`, `.gitignore`, `.env.example`.
- Документация: `docs/{PROJECT, ARCHITECTURE, ROADMAP, STATUS, DEVELOPMENT_LOG, DECISIONS, RESEARCH_VPET, HARDWARE, TESTING, CHANGELOG, PHASE1_PLAN}.md`.
- ADR-001…ADR-005.

### Изменено

— (предыдущих изменений не было).

### Удалено

— ничего.
