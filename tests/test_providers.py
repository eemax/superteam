from __future__ import annotations

from superteam.providers.openrouter.config import OpenRouterConfig
from superteam.providers.openrouter.client import OpenRouterProvider


def test_openrouter_health_false_without_key(monkeypatch):
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    provider = OpenRouterProvider(OpenRouterConfig(api_key=None))
    assert provider.health() is False


def test_openrouter_health_true_with_key():
    provider = OpenRouterProvider(OpenRouterConfig(api_key="test-key"))
    assert provider.health() is True


def test_openrouter_config_defaults():
    cfg = OpenRouterConfig()
    assert cfg.model == "openai/gpt-4o"
    assert cfg.max_tokens == 4096
    assert cfg.base_url == "https://openrouter.ai/api/v1"


def test_openrouter_token_tracking():
    provider = OpenRouterProvider(OpenRouterConfig(api_key="test"))
    assert provider.last_tokens == {}
    provider._extract_usage({"usage": {"prompt_tokens": 10, "completion_tokens": 20, "total_tokens": 30}})
    assert provider.last_tokens == {"input": 10, "output": 20, "total": 30}
