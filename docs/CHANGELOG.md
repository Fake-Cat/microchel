# docs/CHANGELOG.md — изменения проекта

Формат: по датам, новые сверху.

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
