"""CLI Agent Core (PHASE 5): python -m microchel.agent.cli "поручение".

Консольная точка входа без Qt: конфиг → провайдер → реестр → executor → ответ.
Коды выхода: 0 — completed, 1 — failed, 2 — limit_reached, 3 — cancelled.
"""

from __future__ import annotations

import argparse
import json
import logging
import signal
import sys
from dataclasses import asdict
from pathlib import Path

from microchel.agent.config import (
    DEFAULT_CONFIG_PATH,
    AgentConfig,
    AgentConfigError,
    load_agent_config,
    load_dotenv,
)
from microchel.agent.executor import AgentExecutor
from microchel.agent.journal import ExecutionJournal, default_journal_path
from microchel.agent.llm import build_provider
from microchel.agent.llm.fake import FakeProvider
from microchel.agent.types import Limits, TaskSpec, TaskStatus, ToolCall
from microchel.common.logging_config import setup_logging
from microchel.tools import build_default_registry

logger = logging.getLogger(__name__)

EXIT_CODES: dict[TaskStatus, int] = {
    TaskStatus.COMPLETED: 0,
    TaskStatus.FAILED: 1,
    TaskStatus.LIMIT_REACHED: 2,
    TaskStatus.CANCELLED: 3,
}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="microchel.agent.cli",
        description=(
            "CLI Agent Core Микрочела: поручение на естественном языке → LLM + инструменты → ответ"
        ),
    )
    parser.add_argument(
        "prompt", nargs="+", help="Поручение пользователя, например: Проверь состояние компьютера"
    )
    parser.add_argument(
        "--config", type=Path, default=DEFAULT_CONFIG_PATH, help="Путь к agent.toml"
    )
    parser.add_argument("--provider", help="Провайдер LLM: gemini | fake (перекрывает конфиг)")
    parser.add_argument("--model", help="Модель LLM (перекрывает конфиг)")
    parser.add_argument(
        "--proxy", help="URL прокси для LLM-запросов (перекрывает конфиг/окружение)"
    )
    parser.add_argument(
        "--offline", action="store_true", help="Офлайн-демо без сети и ключа (fake-провайдер)"
    )
    parser.add_argument("--json", action="store_true", help="Печатать результат задачи как JSON")
    parser.add_argument("--journal", type=Path, help="Путь к журналу (JSONL)")
    parser.add_argument("--max-steps", type=int, help="Лимит шагов")
    parser.add_argument("--max-llm-calls", type=int, help="Лимит вызовов LLM")
    parser.add_argument("--max-tool-calls", type=int, help="Лимит вызовов инструментов")
    parser.add_argument("--timeout", type=float, help="Общий лимит времени задачи, с")
    parser.add_argument("--tool-timeout", type=float, help="Таймаут одного инструмента, с")
    parser.add_argument(
        "--log-level", default="INFO", help="Уровень логирования (DEBUG/INFO/WARNING/ERROR)"
    )
    return parser


def _demo_provider() -> FakeProvider:
    """Сценарий --offline: сбор метрик инструментом, затем финальный текст."""
    return FakeProvider(
        responses=[
            _tool_call_response("system.metrics"),
            _final_response(),
        ]
    )


def _tool_call_response(name: str):  # noqa: ANN202 — импорт LLMResponse тянет цепочку типов
    from microchel.agent.types import LLMResponse

    return LLMResponse(text="", tool_calls=(ToolCall(id="call_0", name=name, arguments={}),))


def _final_response():  # noqa: ANN202
    from microchel.agent.types import LLMResponse

    return LLMResponse(
        text=(
            "Офлайн-демо: данные компьютера собраны инструментом system.metrics "
            "(см. детали шагов в журнале). LLM не использовался."
        ),
        tool_calls=(),
    )


def _limits_from_args(config: AgentConfig, args: argparse.Namespace) -> Limits:
    limits = config.limits
    updates = {
        field_name: value
        for field_name, value in (
            ("max_steps", args.max_steps),
            ("max_llm_calls", args.max_llm_calls),
            ("max_tool_calls", args.max_tool_calls),
            ("wall_time_s", args.timeout),
            ("tool_timeout_s", args.tool_timeout),
        )
        if value is not None
    }
    return Limits(**{**{f: getattr(limits, f) for f in limits.__dataclass_fields__}, **updates})


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    setup_logging(level=args.log_level)
    load_dotenv(Path.cwd() / ".env")
    load_dotenv(DEFAULT_CONFIG_PATH.parent.parent / ".env")

    try:
        config = load_agent_config(args.config)
        provider = _demo_provider() if args.offline else build_provider(
            config, provider_name=args.provider, model=args.model, proxy_url=args.proxy
        )
    except (AgentConfigError, ValueError) as exc:
        print(f"Ошибка конфигурации: {exc}", file=sys.stderr)
        return 1

    registry = build_default_registry(config.allowed_roots)
    journal_path = args.journal or (
        Path(config.journal_path) if config.journal_path else default_journal_path()
    )
    executor = AgentExecutor(
        provider,
        registry,
        journal=ExecutionJournal(journal_path),
    )

    def _on_sigint(signum: int, frame: object) -> None:  # noqa: ARG001
        logger.warning("Прерывание: завершаю задачу корректно (повторное Ctrl+C — жёсткий выход)")
        executor.cancel()

    signal.signal(signal.SIGINT, _on_sigint)

    spec = TaskSpec(prompt=" ".join(args.prompt), limits=_limits_from_args(config, args))
    result = executor.run(spec)

    if args.json:
        payload = asdict(result)
        payload["status"] = result.status.value
        print(json.dumps(payload, ensure_ascii=False, default=str))
    else:
        if result.answer:
            print(result.answer)
        if result.error:
            print(f"[{result.status.value}] {result.error}", file=sys.stderr)
        print(
            f"-- статус={result.status.value} шагов={len(result.steps)} "
            f"llm={result.llm_calls} tools={result.tool_calls} время={result.elapsed_s}с "
            f"журнал={journal_path}",
            file=sys.stderr,
        )
    return EXIT_CODES[result.status]


if __name__ == "__main__":
    raise SystemExit(main())