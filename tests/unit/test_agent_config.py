"""Тесты конфигурации агента: TOML, дефолты, .env, прокси-резолюция."""

from pathlib import Path

import pytest

from microchel.agent.config import (
    AgentConfig,
    AgentConfigError,
    load_agent_config,
    load_dotenv,
    resolve_proxy_url,
)


def test_defaults() -> None:
    config = AgentConfig()
    assert config.provider == "gemini"
    assert config.api_key_env == "GEMINI_API_KEY"
    assert config.allowed_roots == ()
    assert config.limits.max_steps == 8


def test_load_from_toml(tmp_path: Path) -> None:
    path = tmp_path / "agent.toml"
    path.write_text(
        'provider = "fake"\n'
        'model = "test-model"\n'
        'api_key_env = "TEST_KEY"\n'
        'proxy_url = "http://127.0.0.1:9999"\n'
        'allowed_roots = ["/tmp"]\n'
        "[limits]\n"
        "max_steps = 3\n"
        "tool_timeout_s = 5\n",
        encoding="utf-8",
    )
    config = load_agent_config(path)
    assert config.provider == "fake"
    assert config.model == "test-model"
    assert config.proxy_url == "http://127.0.0.1:9999"
    assert config.allowed_roots == ("/tmp",)
    assert config.limits.max_steps == 3
    assert config.limits.tool_timeout_s == 5
    assert config.limits.max_llm_calls == 12  # не тронутое поле — дефолт


def test_invalid_toml_falls_back_to_defaults(tmp_path: Path) -> None:
    path = tmp_path / "broken.toml"
    path.write_text("это не томл [[", encoding="utf-8")
    config = load_agent_config(path)
    assert config == AgentConfig()


def test_missing_file_falls_back_to_defaults(tmp_path: Path) -> None:
    assert load_agent_config(tmp_path / "нет.toml") == AgentConfig()


def test_api_key_resolution() -> None:
    config = AgentConfig(api_key_env="MY_KEY")
    assert config.api_key(env={"MY_KEY": "abc123"}) == "abc123"
    with pytest.raises(AgentConfigError):
        config.api_key(env={})
    with pytest.raises(AgentConfigError):
        config.api_key(env={"MY_KEY": "   "})


def test_load_dotenv_setdefault(tmp_path: Path) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text("# комментарий\nA=1\nB=2\nбез_равно\n", encoding="utf-8")
    env: dict[str, str] = {"B": "уже есть"}
    result = load_dotenv(env_file, env=env)
    assert result == {"A": "1", "B": "уже есть"}
    assert load_dotenv(tmp_path / "нет.env", env={}) == {}


def test_resolve_proxy_priority() -> None:
    env = {"https_proxy": "http://from-env:1", "http_proxy": "http://from-env-http:1"}
    assert resolve_proxy_url("http://cli:1", "http://config:1", env=env) == "http://cli:1"
    assert resolve_proxy_url(None, "http://config:1", env=env) == "http://config:1"
    assert resolve_proxy_url(None, "", env=env) == "http://from-env:1"
    assert resolve_proxy_url(None, "", env={}) == ""
    assert resolve_proxy_url(None, "", env={"HTTP_PROXY": "http://up:1"}) == "http://up:1"
    assert resolve_proxy_url(None, "", env={"HTTPS_PROXY": "http://up:2"}) == "http://up:2"