# docs/DEVELOPMENT_LOG.md — журнал разработки

Новые записи добавляются сверху. Историю не удалять.

---

## 2026-10-08 — PHASE 2: Animation Engine (код)

**Цель:** движок анимаций по docs/PHASE2_PLAN.md. Команда пользователя получена («Да, начинаем PHASE 2»).

**Выполненные действия:**

1. Создан `docs/PHASE2_PLAN.md` (требования FR-P2.1…NF-P2.5, архитектура, критерии), ROADMAP переведён в «текущий».
2. `scripts/make_test_animations.py` — генератор демо-клипов (idle/blink/walk, 17 кадров, длительности 60–375 мс, свой материал).
3. Пакет `src/microchel/animation/`:
   - `frames.py` — парсер `_NNN_DDD.png` (ADR-005), `load_clip` (имя «Анимация/Состояние», линии), `discover_clip_dirs`.
   - `cache.py` — `FrameCache`: LRU по байтам, ленивая загрузка, вытеснение, purge/invalidate, счётчики hit/miss (без Qt — загрузчик-колбэк).
   - `queue.py` — `Priority` (IDLE<BEHAVIOR<EVENT<REACTION), `AnimationRequest`, heap-очередь с FIFO внутри приоритета.
   - `player.py` — `AnimationPlayer(QObject)`: single-shot QTimer по длительности кадра из имени файла, loop (∞/N/1), прерывание на границе кадра (pending), возврат к idle, сигналы `frame_changed/started/finished`.
4. `desktop/window.py` — `setup_animation()`, показ кадра вместо статичного спрайта, автоподстройка размера под кадр с сохранением центра, `play_clip(prefix)`.
5. `desktop/main.py` — `--demo` (случайные blink/walk каждые 4 с, возврат к idle).
6. Тесты: `test_frames.py` (19), `test_cache.py` (8), `test_queue.py` (6), `test_player.py` (9), `test_window.py` (+4) — итог **77 passed**, ruff чисто.

**Технические проблемы:**

- `QPixmap.sizeInBytes()` отсутствует в PySide6 (это метод QImage) → расчёт `w*h*depth//8`.
- Имя клипа бралось с неверного уровня иерархии («Happy/1» вместо «Idle/Happy») — исправлено на два уровня над линией.
- Плеер с parent-виджетом в фикстуре «умирал» до теста → `AnimationPlayer()` без parent (ссылку держит фикстура).
- Ошибки черновика в тестах (`-> None` без двоеточия, заглушка) — вычищены до зелёного прогона.

**Результаты тестов (фактически):**

- `pytest` — **77 passed**; `ruff check .` — All checks passed.
- Генерация ассетов: 3 клипа / 17 кадров сохранены.
- Запуск `--demo` (PID 2336194): лог подтверждает переключения Walk/Blink каждые 4 с и возврат к idle; **RSS 103080 → 104352 kB за 60 с** (рост ~1.2 MB — шум, не линейный разлив). Долгий замер (≥10 мин) — продолжается, итог в TESTING.md.

**Итог (закрытие):** сценарии P2-1…P2-4 подтверждены пользователем («всё остальное довольно хорошо»); **замечание: неплавность вертикального движения (idle/walk)** → TESTING «Известные ошибки» №1, улучшение — в PHASE 4. Финальный замер: RSS **104356 kB** на 6-й минуте (после 1-й минуты роста нет), 89 демо-переключений. **PHASE 2 закрыт 2026-10-08.**

**Незавершённые вопросы:**

— нет; P2-6 (чистый выход) подтвердится при следующем закрытии окна.

**Следующие шаги:** по команде — PHASE 3 (Character Behavior).

---

## 2026-10-08 — PHASE 1: Minimal Desktop Pet (код)

**Цель:** минимальный GUI-прототип по docs/PHASE1_PLAN.md. Решение пользователя: **запуск локально, без Docker** (визуальные тесты — на реальном Wayland-стенде).

**Выполненные действия:**

1. `common/logging_config.py` — структурированное логирование, уровень из MICROCHEL_LOG_LEVEL.
2. `desktop/geometry.py` — чистые функции `clamp_axis`, `clamp_to_screen` (тестируются без GUI).
3. `desktop/window.py` — `PetWindow`: frameless + always-on-top + WA_TranslucentBackground, отрисовка QPixmap в paintEvent, перетаскивание ЛКМ через смещение, `move_clamped` к availableGeometry, контекстное меню `build_menu()` с пунктом «Выход».
4. `desktop/main.py` — точка входа `python -m microchel.desktop.main`, логирует `app.platformName()`.
5. `scripts/make_test_sprite.py` — генерация тестового chibi-спрайта Qt-Painter'ом (160×160 RGBA, свой материал, лицензия не вопрос), вывод `assets/characters/test/test_idle.png`.
6. Тесты: `tests/unit/test_geometry.py` (6 кейсов, включая мультимониторный), `tests/integration/test_window.py` (pytest-qt: флаги, прозрачность, загрузка спрайта, зажим координат, меню).

**Изменённые компоненты:** desktop/, common/, scripts/, tests/, assets/ (спрайт).

**Технические проблемы:**

- Ошибка ruff E501 (2 линии) — исправлено переносами.
- Черновик `make_test_sprite.py` был создан с ошибочным импортом — переписан полностью.
- Запуск под Wayland: предупреждения `qt.qpa.wayland.textinput` — безобидные.
- **Перетаскивание под нативным Wayland не работало** (жалоба пользователя): диагностика показала, что события мыши доходят (689 записей), но композитор игнорирует `move()` — ограничение Wayland (ADR-002). Фикс: `QT_QPA_PLATFORM=xcb`; для xcb не хватало `libxcb-cursor0` — пакет установлен пользователем (согласовано). После перезапуска под xcb **драг подтверждён пользователем**.
- В `main.py` добавлен `select_qt_platform()`: под Wayland-сессией по умолчанию xcb, явный `QT_QPA_PLATFORM` не перетирается (+5 юнит-тестов).

**Принятые решения:** решение о локальном (не Docker) запуске визуальных тестов — по слову пользователя; авто-запуск через xcb под Wayland (ADR-002, уточнён); **лицензия проекта — MIT** (LICENSE, pyproject `license = "MIT"`, README) — выбор пользователя 2026-10-08.

**Результаты тестов (фактически):**

- `pytest` — **31 passed** (smoke + geometry + window + main).
- `ruff check .` — **All checks passed**.
- Спрайт — PNG 160×160 RGBA сохранён.
- Нативный запуск — wayland: окно видно, но драг невозможен → **xcb: всё OK** (лог /tmp/microchel_gui.log).
- Ручные сценарии **1–6 — все OK** (пользователь, 2026-10-08): прозрачность ✅, драг ✅, always-on-top ✅, меню «Выход» ✅, чистый выход ✅.
- **Мультимонитор (3 экрана):** выявлено, что зажим «прилипает» к одному экрану; добавлен `desktop_area()` (объединение рабочих областей всех экранов), тесты на мультимониторную геометрию; проверено пользователем — пит переезжает между мониторами (в логе: x=4528).

**Незавершённые вопросы:**

— нет; Git: коммиты `9302f3f` (bootstrap) и `987c3a8` (PHASE 1) созданы, лицензия MIT (2026-10-08).

**Следующие шаги:** PHASE 1 закрыт → по команде PHASE 2 (Animation Engine).

---

## 2026-10-08 — PHASE 0: Research & Bootstrap

**Цель:** выполнить PHASE 0 по концепции (docs/concept.md, раздел 16).

**Выполненные действия:**

1. Исследовано окружение: Ubuntu 26.04.1 x86-64, Python 3.14.4, Git 2.53.0, сессия **Wayland** (не X11!), XWayland :0 доступен, сеть есть, pytest 9.0.2 есть, PySide6 и ruff отсутствуют.
2. Проверен Git: ветка `main`, коммитов нет, неотслеживаемы `docs/`.
3. Создана структура каталогов: `src/microchel/{desktop,animation,character,agent,tools,voice,monitoring,memory,common}`, `assets/{characters,audio}`, `config`, `docs/decisions`, `tests/{unit,integration}`, `scripts`, `packaging` (+ `__init__.py`).
4. Создана документация: AGENTS.md, README.md, docs/{PROJECT, ARCHITECTURE, ROADMAP, STATUS, DEVELOPMENT_LOG, DECISIONS, RESEARCH_VPET, HARDWARE, TESTING, CHANGELOG, PHASE1_PLAN}.md, ADR-001…005.
5. Подготовлены pyproject.toml, .gitignore, .env.example.
6. Исследован VPet через GitHub API (без клонирования 1.4 GB): см. RESEARCH_VPET.md.

**Изменённые компоненты:** только документация и инфраструктура; кода нет.

**Технические проблемы:**

- Сессия Wayland — риск для прозрачных always-on-top окон (риск PHASE 1, ADR-002).
- PySide6 не установлен; установка в `.venv` через pip — план PHASE 1 (не системные пакеты, разрешено).

**Принятые решения:** ADR-001…ADR-005 (см. docs/DECISIONS.md).

**Результаты тестов (фактически, 2026-10-08):**

- `pip install -e ".[dev]"` в `.venv` — успешно (PySide6 6.12.0 / Qt 6.12.0, pytest 9.1.1, pytest-qt 4.5.0, ruff 0.16.10).
- Smoke: импорт PySide6.QtCore — OK; `QApplication` в offscreen-режиме — OK.
- `pytest` — **2 passed** (tests/unit/test_smoke.py).
- `ruff check .` — **All checks passed**.
- Ручные GUI-сценарии TESTING.md — не проводились (окна ещё нет, это PHASE 1).

**Незавершённые вопросы:**

- Лицензия собственного кода (MIT?Apache-2.0?) — спросить пользователя.
- Формат хранения ресурсов: нативный формат VPet (`_NNN_DDD.png`) или свой — решить в PHASE 2.
- Коммитить ли bootstrap в Git — спросить пользователя (по умолчанию не коммичу).

**Следующие шаги:** ждать команды на PHASE 1 (см. PHASE1_PLAN.md).
