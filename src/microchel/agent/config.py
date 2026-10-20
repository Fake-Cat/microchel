"""Конфигурация Agent Core (PHASE 5): config/agent.toml + секреты из окружения.

Паттерн как у character/config.py: дефолты живут в dataclass, TOML-файл их
перекрывает; битый/отсутствующий файл → дефолты + предупреждение, не крах.
API-ключи НИКОГДА не хранятся в конфиге — только в окружении/.env
(имя переменной задаётся api_key_env). Прокси: cli --proxy > proxy_url в
конфиге > https_proxy/http_proxy окружения > прямое подключение (ADR-006).
"""

from __future__ import annotations

import logging
import os
import tomllib
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any

from microchel.agent.types import Limits

logger = logging.getLogger(__name__)

DEFAULT_CONFIG_PATH = Path(__file__).resolve().parents[3] / "config" / "agent.toml"

KNOWN_PROVIDERS = ("gemini", "fake")


class AgentConfigError(Exception):
    """Неконфигурируемое состояние (например, отсутствует API-ключ)."""


@dataclass(frozen=True, slots=True)
class AgentConfig:
    """Настройки Agent Core; секреты — только через api_key_env + окружение."""

    provider: str = "gemini"
    model: str = "gemini-3.8-flash"
    api_key_env: str = "GEMINI_API_KEY"
    base_url: str = ""  # пусто → дефолтный URL провайдера
    proxy_url: str = ""  # пусто → https_proxy/http_proxy окружения, иначе прямой
    allowed_roots: tuple[str, ...] = ()  # каталоги для files.* (пусто → чтение запрещено)
    journal_path: str = ""  # пусто → ~/.local/share/microchel/agent_journal.jsonl
    limits: Limits = field(default_factory=Limits)

    def api_key(self, env: dict[str, str] | None = None) -> str:
        """Ключ из окружения; отсутствие — явная ошибка, не падение посреди задачи."""
        source = os.environ if env is None else env
        key = source.get(self.api_key_env, "").strip()
        if not key:
            raise AgentConfigError(
                f"API-ключ не найден: переменная {self.api_key_env} пуста или отсутствует. "
                "Положите ключ в .env (см. .env.example) или экспортируйте в окружение."
            )
        return key


def load_dotenv(path: Path | str = ".env", env: dict[str, str] | None = None) -> dict[str, str]:
    """Загрузить .env в окружение (setdefault: экспортированное не перетирается)."""
    target = os.environ if env is None else env
    file_path = Path(path)
    if not file_path.is_file():
        return target
    for raw_line in file_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        target.setdefault(key.strip(), value.strip())
    return target


def resolve_proxy_url(
    cli_proxy: str | None = None,
    config_proxy: str = "",
    env: dict[str, str] | None = None,
) -> str:
    """Приоритет прокси: CLI > конфиг > https_proxy/http_proxy окружения > прямой."""
    if cli_proxy:
        return cli_proxy.strip()
    if config_proxy:
        return config_proxy.strip()
    source = os.environ if env is None else env
    return (
        source.get("https_proxy")
        or source.get("HTTPS_PROXY")
        or source.get("http_proxy")
        or source.get("HTTP_PROXY")
        or ""
    ).strip()


def load_agent_config(path: Path | str | None = None) -> AgentConfig:
    """Загрузить config/agent.toml; ошибки файла → дефолты + предупреждение."""
    file_path = DEFAULT_CONFIG_PATH if path is None else Path(path)
    config = AgentConfig()
    if not file_path.is_file():
        logger.warning("Конфиг агента не найден (%s) — использую дефолты", file_path)
        return config
    try:
        with file_path.open("rb") as handle:
            raw: dict[str, Any] = tomllib.load(handle)
    except (tomllib.TOMLDecodeError, OSError):
        logger.warning(
            "Конфиг агента не читается (%s) — использую дефолты", file_path, exc_info=True
        )
        return config

    limits_raw = raw.get("limits", {})
    limits = config.limits
    if isinstance(limits_raw, dict):
        updates = {
            name: limits_raw[name]
            for name in limits.__dataclass_fields__
            if name in limits_raw and isinstance(limits_raw[name], (int, float))
        }
        if updates:
            limits = replace(limits, **updates)

    roots_raw = raw.get("allowed_roots", [])
    roots = tuple(str(item) for item in roots_raw) if isinstance(roots_raw, list) else ()

    provider = str(raw.get("provider", config.provider))
    if provider not in KNOWN_PROVIDERS:
        logger.warning(
            "Неизвестный провайдер %r в %s — ожидаются %s", provider, file_path, KNOWN_PROVIDERS
        )

    return replace(
        config,
        provider=provider,
        model=str(raw.get("model", config.model)),
        api_key_env=str(raw.get("api_key_env", config.api_key_env)),
        base_url=str(raw.get("base_url", config.base_url)),
        proxy_url=str(raw.get("proxy_url", config.proxy_url)),
        allowed_roots=roots,
        journal_path=str(raw.get("journal_path", config.journal_path)),
        limits=limits,
    )