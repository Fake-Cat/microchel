# docs/PHASE5_PLAN.md — план PHASE 5: AI Agent Core (спринт 5.1)

**Цель PHASE 5:** автономный ИИ-агент: поручения на естественном языке → LLM (tool calling) → безопасные инструменты → ответ. GUI не связан с LLM напрямую (ADR-003). **Спринт 5.1 (этот документ):** GUI-независимое Agent Core — CLI, Gemini-провайдер, цикл tool calling, безопасные инструменты. PHASE 4 приостановлена по команде пользователя (2026-10-11).

**Команда пользователя:** получена 2026-10-11 (спринт 5.1 — CLI Agent Core без GUI).

## Требования спринта 5.1

### Функциональные

- **FR-P5.1 Провайдер LLM:** интерфейс `LLMProvider` (Protocol) + иерархия ошибок `LLMError` (`LLMAuthError`, `LLMRateLimitError`, `LLMNetworkError`, `LLMProtocolError`) — чистый слой, без Qt. Реализация **Gemini** (`generateContent`, functionDeclarations из ToolSpec, round-trip `thoughtSignature` на уровне part — обязательно для повторных вызовов!). FakeProvider — офлайн-демо/тесты без сети.
- **FR-P5.2 Конфигурация:** `config/agent.toml` (tomllib): провайдер, модель, `api_key_env` (секрет — только в окружении/.env), прокси, `allowed_roots`, `journal_path`, бюджеты `[limits]`. Отсутствующий/битый конфиг → дефолты + предупреждение. Резолюция прокси — ADR-006.
- **FR-P5.3 Инструменты (безопасные):** `system.metrics` (CPU/память/диск/uptime/температура, `/proc`,`/sys`), `files.read`, `files.list` (только чтение, только `allowed_roots`, лимит байт, бинарь отсекается), `services.status` (`systemctl show`, shell=False, regex-валидация имени ≤256 символов — анти injection). Опасные операции (запись, удаление, shell) — **не входят**; permissions-слой — спринт 5.2.
- **FR-P5.4 Tool registry:** реестр схем (имя, описание, JSON-schema аргументов), валидация аргументов, изоляция ошибок инструмента (исключение → `ToolResult(ok=False)`, задача не падает), таймаут исполнения.
- **FR-P5.5 Цикл исполнения (AgentExecutor):** задача на естественном языке → SYSTEM_PROMPT → цикл LLM↔инструменты; бюджеты `max_steps`/`max_llm_calls`/`max_tool_calls`/`wall_time_s`; отмена через `threading.Event` (SIGINT → cancel); вывод инструментов усечён (`max_tool_output_chars`); события `UserPrompt`/`AgentTaskStarted`/`AgentTaskFinished` в EventBus; журнал `ExecutionJournal` (JSONL).
- **FR-P5.6 CLI:** `python -m microchel.agent.cli "поручение"` — аргументы `--config`, `--proxy`, `--journal`, `--offline`, `--json`, `--log-level`; коды выхода: 0 — успех, 1 — ошибка LLM/сети, 2 — неверные аргументы, 3 — сбой инструмента/исполнение. **Не импортирует PySide6** (проверено тестом).

### Нефункциональные

- **NF-P5.1:** Python type hints, только stdlib для сети (urllib) — без новых тяжёлых зависимостей, ARM64-совместимо.
- **NF-P5.2:** длинные операции не блокируют ничей event loop (CLI — синхронный, но без Qt; GUI-интеграция — будущий спринт через QThread, ADR-003).
- **NF-P5.3:** тестируемость — провайдер через подмену `post_json`, инструменты через runner-подмену, executor через FakeProvider; pytest без сети.
- **NF-P5.4:** секреты не попадают в логи/журнал/конфиг.

### Явно НЕ входит в спринт 5.1

GUI-интеграция (отдельный спринт), permissions/подтверждение опасных операций, memory (SQLite), полная политика prompt injection (базовая защита — guard) — спринт 5.2; другие провайдеры (Groq/OpenRouter — при необходимости), голос, мониторинг.

## Архитектура (структура кода)

```
src/microchel/agent/
├── types.py        # чистое: TaskSpec, TaskResult, StepRecord, ToolCall, Limits…
├── config.py       # чистое: AgentConfig + загрузка config/agent.toml, resolve_proxy_url
├── prompt.py       # чистое: SYSTEM_PROMPT
├── journal.py      # чистое: ExecutionJournal (JSONL, отказ записи — warning)
├── executor.py     # чистый цикл LLM↔инструменты, события, бюджеты, cancel
├── cli.py          # argparse CLI (без Qt)
└── llm/
    ├── base.py     # LLMError + LLMProvider Protocol
    ├── http.py     # urllib, ProxyHandler, ретрай 1 раз на 429/503
    ├── gemini.py   # generateContent, functionDeclarations, thoughtSignature
    └── fake.py     # офлайн-сценарий
src/microchel/tools/
├── base.py         # ToolSpec, ToolResult, Tool Protocol
├── guard.py        # PathGuard: allowed_roots, лимит чтения, анти path traversal
├── registry.py     # ToolRegistry: схемы, валидация, таймаут
├── system_metrics.py, file_read.py, services.py
config/agent.toml
```

## План шагов (спринт 5.1)

0. ✅ Точка отсчёта: чистое дерево (коммит `85b3631`, PHASE 4).
1. Документация: этот план, ADR-006, ARCHITECTURE, STATUS/ROADMAP/TESTING/DEVELOPMENT_LOG.
2. ✅ События PHASE 5 в `common/events.py`.
3. ✅ `agent/types.py`, `agent/config.py`, `agent/journal.py`, `config/agent.toml`.
4. ✅ `tools/base.py`, `tools/guard.py`, `tools/registry.py`.
5. ✅ Инструменты: `system_metrics.py`, `file_read.py`, `services.py`.
6. ✅ LLM-слой: `base.py`, `http.py`, `fake.py`, `gemini.py`.
7. ✅ `agent/prompt.py`, `agent/executor.py`.
8. ✅ `agent/cli.py` + интеграционный тест (вкл. «PySide6 не импортируется»).
9. ✅ Проверки: `ruff` — чисто; `pytest` — **376 passed**; живой прогон с Gemini.

## Критерии приёмки

- `pytest` без сети зелёный; `ruff` чистый. ✅
- `python -m microchel.agent.cli --offline …` → exit 0, статус completed, данные собраны `system.metrics`. ✅
- Живой прогон с Gemini через прокси: `--proxy http://127.0.0.1:1081 "Проверь состояние этого компьютера"` → модель выбирает `system.metrics` (или `services.status`), реальные данные в ответе, exit 0, статус completed. ✅ (2026-10-11: CPU 57°C, RAM 51/61 ГБ, диск, uptime 24.5 ч)
- Отказ сети/ключа: понятная ошибка, код выхода 1/3, CLI не зависает. ✅

## Известные особенности

- Gemini требует `thoughtSignature` в `functionCall`-частях при отправке истории — без него второй вызов падает с 400. Поддерживается round-trip (part-уровень).
- Gemini из РФ недоступен напрямую — нужен прокси (`http://127.0.0.1:1081`); `llm_timeout_s` в конфиге увеличен до 120 (медленный прокси).
- Журнал по умолчанию: `~/.local/share/microchel/agent_journal.jsonl` (XDG); необязателен — отказ записи не роняет задачу.

