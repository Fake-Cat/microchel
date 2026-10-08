# docs/DEVELOPMENT_LOG.md — журнал разработки

Новые записи добавляются сверху. Историю не удалять.

---

## 2026-10-08 — PHASE 3: шаг 10 (ручные сценарии P3-1…P3-7) и фикс загрузки конфига

**Цель:** шаг 10 плана PHASE 3 — живые сценарии P3 и замечания пользователя.

**Выполненные действия:**

1. Флаг `--showcase` (показ всех клипов по 10 с, взаимоисключен с `--demo`) + фикс сортировки (Idle первым).
2. Фоновый прогон ≥10 мин (`--demo-events`, лог `/tmp/microchel_gui.log`, мониторинг позиции/RSS каждые 5/60 с): **P3-1** — переходы всех состояний без участия, 0 ошибок; **P3-5** — 13+ событий, интервалы 47–89 с; **P3-6** — ночь, сон доминировал (14,4 мин из наблюдаемого окна); **P3-7** — RSS 104,5→105,5 МБ. **P3-3/P3-4** — клик и драг подтверждены пользователем.
3. **Баг (вскрыт при попытке временно отключить ночь ради P3-2):** `main.py` вызывал `load_behavior_config()` без пути → `path=None` → всегда `BehaviorConfig()` — правки `config/behavior.toml` **не влияли на приложение** (тесты зелёные: файл зеркалит дефолты, `test_default_config_file_exists_and_loads`). Фикс: `load_behavior_config(DEFAULT_CONFIG_PATH)`; регресс-тест `test_start_behavior_loads_config_file` (monkeypatch spy, ловит переданный путь).
4. **P3-2:** ночь временно отключена (`from = to = 12`), пит у правого края (x=5500, максимум 5600): `idle → walk (5276 мс)` → DEBUG «Ходьба: позиция не изменилась, разворот → -1» → позиции 5500→5563→5447 (движение глазами подтверждено). Конфиг **восстановлен** (23/8) — после восстановления `test_default_config_file_exists_and_loads` проходит.
5. Наблюдение «ночью просыпается на секунду и резко дёргается»: это blink-реакция `--demo-events` (~570 мс, стоячая поза ассета) поверх Sleep с приоритетом EVENT; сон FSM не прерывается. Записано в TESTING.md «Известные ошибки» №3 → PHASE 4.
6. Документация: STATUS.md, ROADMAP.md (шаг 10 [x]), TESTING.md (таблица P3 заполнена, №3, результаты), CHANGELOG.md.
7. Пользователь предоставил референс внешности/фонов `docs/Микрочел_ питомец на Raspberry Pi.png` (подтверждено: собственный материал → можно в репозиторий). Идея: **фон-задник за персонажем** для отдельных состояний/эмоций/задач — записана в ROADMAP (PHASE 4) с подходом «слой `bg.png` рядом с клипом, рисуется под кадром».

**Технические проблемы и как решены:**

- Скриншоты на dev-стенде невозможны (нет grim/scrot; ffmpeg x11grab под Wayland → чёрный кадр) — верификация логами + `xwininfo` (xdotool отсутствует) + глазами пользователя.
- Перед P3-2 дважды выпал сон при первом выходе из idle (RNG, 10%) — перезапуски; строка разворота — только на `--log-level DEBUG`.
- «Пит не двигается» первой ночью — не баг ходьбы, а ночь (вес 300 → сон ~77%) + дневной прогон был в 23:00+; развязка — отключение ночи для P3-2 с восстановлением конфига.

**Результаты тестов (фактически):** `pytest` — **167 passed**; `ruff check .` — All checks passed.

**Следующие шаги:** шаг 11 — коммит PHASE 3 по команде пользователя.

---

## 2026-10-08 — PHASE 3: Character Behavior (код, шаги 1–9)

**Цель:** FSM поведения по docs/PHASE3_PLAN.md (шаги 1–11). Команда пользователя получена 2026-10-08.

**Выполненные действия:**

1. **Шаги 1–2:** план/документы; `common/events.py` (`UserEvent`, `SystemEvent`, `CharacterAction` — frozen dataclass, slots) + `common/event_bus.py` (синхронная шина, подписка по типу, ошибки обработчиков — в лог) + тесты.
2. **Шаг 3:** `character/states.py` — `CharacterState` (StrEnum), `STATE_CLIP_PREFIX`/`STATE_PRIORITY`/`TRANSIENT_STATES`, `clip_prefix_for` + тесты (деградация, полнота маппинга).
3. **Шаг 4:** `character/config.py` (`BehaviorConfig` — frozen slots dataclass; `load_behavior_config` c tomllib: битые значения → дефолт + лог) + `config/behavior.toml` + тесты (15). **Решение пользователя:** ночью `night.sleep_weight = 300` → сон ~78% ночью.
4. **Шаг 5:** `character/fsm.py` — `BehaviorFSM` (инъекция `rng`/`available`/`hour` → детерминизм в тестах), `state_duration_ms`, `on_timeout` (нетерминальное → idle; idle → `rng.choices` по весам), `on_user_event` (DRAG_START прерывает только WALK), `force`, `is_night` + тесты (достижимость состояний, ночь → SLEEP, прерывание).
5. **Шаг 6:** `character/controller.py` — `CharacterController(QObject)`: single-shot таймер состояния + таймер шага ходьбы (2 QTimer, NF-P3.2), подписка на шину, `CharacterAction` на каждую смену, реакция на клик (отложенный показ клипа состояния до `notify_animation_finished`), `SystemEvent` → приоритет EVENT; чистый `EdgeWalker` (разворот: сдвиг не удался → смена направления) + юнит-тесты и pytest-qt интеграция (заглушки play/move).
6. **Шаг 6 (правки плеера — вскрытые интеграцией):** (а) `play(restart=True)` — немедленная замена **другого** клипа тоже (иначе переходы loop-состояний с равным приоритетом застревали в очереди); (б) `_start_next` не запускает idle-фоллбэк, если слушатель `animation_finished` уже запустил клип (иначе состояние после реакции перетиралось). `window.play_clip` получил параметр `restart`.
7. **Шаг 7:** `scripts/make_test_animations.py` — позы (`stand/sit/lie`), глаза `up`, «Z» (сон), кружка (coffee), пузырьки мысли; клипы **Sleep/Sit/Coffee/Thinking** — итого 7 клипов, все грузятся.
8. **Шаг 8:** `desktop/window.py` — `bus` в конструкторе, клик (ЛКМ без смещения ≥ 5 px нет) / `DRAG_START` (порог `DRAG_THRESHOLD_PX=5`) / `DRAG_END` → события в шину, `move_by(dx) -> bool` для ходьбы; `desktop/main.py` — `states_with_clips` (нет клипа → состояние исключено + warning), `start_behavior` (FSM+controller+плеер), `start_demo_events` (SystemEvent SYNTHETIC раз в 45–90 с), флаг `--demo-events`; `--demo` отключает FSM (FR-P3.8) с логом.
9. **Шаг 9:** тесты — новые `test_events/states/behavior_config/fsm/controller` (unit), `test_character_controller/start_behavior/demo_events` (integration), расширены `test_player` (+2: семантика restart, защита слушателя finished), `test_window` (+6: move_by, клик/дрег→шина), `test_main` (+3: флаги, `states_with_clips`). Итог **162 passed, ruff чисто**.
10. **Smoke (offscreen):** 20 с — старт без ошибок, «Поведение подключено», все 6 состояний; 90 с — реальные переходы `idle (51.8 с) → walk (11 с) → idle`, клипы Idle→Walk→Idle в логе, 0 ошибок (`/tmp/microchel_smoke_p3_long.log`).

**Технические проблемы и как решены:**

- «Зацикливание» визуального состояния: переход Sit→Idle c приоритетом IDLE уходил в очередь за looping Sit и не воспроизводился → state-клипы играются с `restart=True` (немедленная замена); приоритеты очереди остаются для REACTION/EVENT.
- Клик во время реакции: повторный клип — no-op (не стакается); смена состояния во время реакции откладывает показ клипа до `notify_animation_finished` (иначе очередь плеера отдала бы устаревший клип).
- Вставка в редакторе >6000 символов — файлы писались частями; одна вставка по неверной строке рассекла тестовый файл — восстановлено, впредь вставки в конец только после фактического счётчика строк.
- `vars()` не работает со `slots=True` — ассерт в тесте конфига заменён на равенство `load_behavior_config(DEFAULT_CONFIG_PATH) == BehaviorConfig()`.
- Лог FSM «idle → idle» (логирование после присваивания) — исправлено на `previous.value`.

**Результаты тестов (фактически):**

- `pytest` — **162 passed** (было 77 → +85 за PHASE 3); `ruff check .` — All checks passed.
- Генерация ассетов: 7 клипов (26 кадров новых + 17 старых перегенерированы).
- Smoke: см. п. 10 выше; RSS в ручных сценариях (шаг 10) — не замерялся.

**Незавершённые вопросы:**

- Шаг 10: ручные сценарии P3-1…P3-7 (≥10 мин, RSS, ночь) — **ждут пользователя**.
- Шаг 11: коммит (по команде); документация уже обновлена (ARCHITECTURE/STATUS/ROADMAP/TESTING/CHANGELOG).

**Следующие шаги:** прогнать P3-1…P3-7 → закрыть PHASE 3 → коммит.

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
