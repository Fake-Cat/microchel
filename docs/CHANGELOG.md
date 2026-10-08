# docs/CHANGELOG.md — изменения проекта

Формат: по датам, новые сверху.

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
