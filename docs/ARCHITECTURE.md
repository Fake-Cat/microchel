# docs/ARCHITECTURE.md — архитектура Microchel

> Статус: **проектирование (PHASE 0)**. Ни один компонент ещё не реализован. Документ описывает целевую архитектуру; по мере реализации разделы обновляются, нереализованное явно помечается.

## Схема компонентов

```
┌────────────────────────────────────────────────────────────┐
│ desktop (PySide6) — прозрачное окно, ввод, меню, drag      │
└───────────────┬────────────────────────────────────────────┘
                │ только события/запросы (никакой LLM)
┌───────────────▼───────────────┐   ┌────────────────────────┐
│ character — FSM поведения,    │   │ animation — плеер      │
│ эмоции, автономный выбор      │──▶│ спрайтов, кэш, FPS     │
└───────────────┬───────────────┘   └────────────────────────┘
                │ события через common/event_bus
┌───────────────▼────────────────────────────────────────────┐
│ agent — ядро агента: LLM provider adapters, цикл задач,    │
│ permission policy, лимиты шагов (отдельные потоки)          │
└───────────────┬────────────────────────────────────────────┘
                │ вызовы инструментов
┌───────────────▼───────────────┐   ┌────────────────────────┐
│ tools — tool registry, схемы, │   │ monitoring — метрики,  │
│ валидация, журнал (без LLM)   │   │ расписания, алерты     │
└───────────────┬───────────────┘   └────────────────────────┘
                │
┌───────────────▼────────────────────────────────────────────┐
│ memory — SQLite (история, задачи, события, настройки)       │
└────────────────────────────────────────────────────────────┘
common/ — event bus, конфигурация, логирование, типы событий
voice/ — STT/TTS/wake word (поздние этапы)
```

## Модель данных процесса

Один процесс Python, один Qt event loop в главном потоке. Долгие операции (LLM, инструменты, мониторинг) — в `QThread`/`QThreadPool` либо отдельном процессе через `multiprocessing`. GUI никогда не ждёт сеть синхронно.

## Форматы событий (зафиксировано в PHASE 3)

События — frozen dataclass в `common/events.py`, доставка через синхронный `common/event_bus.py` (главный поток, подписка по типу):

- `UserEvent(kind)` — пользователь: `CLICK`, `DRAG_START`, `DRAG_END` (окно → контроллер).
- `SystemEvent(kind, payload)` — системное: до PHASE 7 только `SYNTHETIC` (`--demo-events`).
- `CharacterAction(action)` — действие FSM наружу (`walk`, `sleep`, …; в PHASE 5 свяжется с агентом).
- `AgentTaskStarted/AgentTaskFinished(task_id, status)` и `UserPrompt(text)` — PHASE 5, реализовано (спринт 5.1, `agent/executor.py` + `agent/cli.py`).

Поток событий: `PetWindow` (клик/драг) → `EventBus.emit(UserEvent)` → `CharacterController` → `fsm.on_event()` → смена состояния → колбэки `play(...)`/`move_by(dx)` → плеер/окно. Анимационные запросы — НЕ события шины: контроллер вызывает плеер напрямую колбэком, приоритеты `animation/queue.py::Priority` (reaction > event > behavior > idle).

## Модель состояний персонажа (уточнена в PHASE 3)

FSM реализован в `character/` (чистое ядро без Qt): `CharacterState` = `IDLE, WALK, SLEEP, SIT, COFFEE, THINKING` (`states.py`), тайминги/веса/ночь — `config/behavior.toml` (`config.py`), выбор — `fsm.py` (seeded `random.Random`, ночь через `hour`-колбэк), Qt-клей — `controller.py` (2 QTimer, подписка на шину, разворот у края `EdgeWalker`). Состояния: IDLE ↔ одноразовые (после окончания — возврат в IDLE); клип состояния с `loop=True`, приоритет BEHAVIOR (idle-состояние — IDLE); реакция на клик — REACTION поверх состояния с возвратом к нему. Доступность состояния определяется наличием клипа (нет клипа → состояние пропущено с предупреждением, FR-P3.1). `WAKE`, `TYPING`, `TALKING` и эмоциональные реакции `HAPPY, ANGRY, PANIC, SUCCESS, ERROR` (как приоритетные перекрывающие анимации) — PHASE 4/5.

## Обоснование решений

См. `docs/DECISIONS.md` и `docs/decisions/` (ADR-001…ADR-006): Python+PySide6, оконный протокол, отделение Agent Core, ресурсы VPet, формат кадров PNG с длительностью в имени файла, резолюция прокси для LLM (ADR-006).

## Что реализовано (честный список)

- **PHASE 0**: структура репозитория, вся документация, ADR-001…005, pyproject.toml, окружение (.venv).
- **PHASE 1**: `desktop/main.py` (точка входа), `desktop/window.py` (`PetWindow` — frameless, прозрачность, always-on-top флаг, drag с зажимом координат, меню «Выход»), `desktop/geometry.py` (чистая геометрия), `common/logging_config.py`, генератор тестового спрайта.
- **PHASE 2**: пакет `animation/` — `frames.py` (загрузчик кадров `_NNN_DDD.png`), `cache.py` (LRU-кэш ресурсов), `queue.py` (приоритеты запросов), `player.py` (плеер с таймингами из имён файлов, loop, переходами); интеграция в `PetWindow` (показ кадров, автоподстройка размера), `--demo` в точке входа; 77 тестов.
- **PHASE 3 (код)**: `common/events.py` + `common/event_bus.py` (типы событий, синхронная шина); `character/` — `states.py` (enum + маппинг состояние→клип), `config.py` + `config/behavior.toml` (тайминги/веса/ночь, tomllib), `fsm.py` (автономный взвешенный выбор, seeded Random), `controller.py` (QTimer-тик, ходьба с разворотом, реакции); клик/драг → события в окне; `--demo` (отключает FSM) и `--demo-events` в точке входа; клипы Sleep/Sit/Coffee/Thinking; 162 теста. Ручные сценарии P3 — в TESTING.md.
- **PHASE 5, спринт 5.1 (Agent Core, CLI)**: `agent/` — `types.py`, `config.py` (agent.toml + ADR-006 прокси), `prompt.py`, `journal.py` (JSONL), `executor.py` (цикл LLM↔инструменты, бюджеты, cancel), `cli.py` (без Qt); `agent/llm/` — base (LLMError+Protocol), http (urllib+прокси+ретрай), gemini (functionDeclarations, thoughtSignature), fake (офлайн); `tools/` — base/guard/registry + system.metrics, files.read/list (чтение), services.status (systemctl show, shell=False); 376 тестов. План: `docs/PHASE5_PLAN.md`.
- **Не реализовано**: GUI-интеграция агента, permissions (опасные операции), memory (SQLite), voice, monitoring, эмоции/WAKE (PHASE 4) — см. ROADMAP.md.
