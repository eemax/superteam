from __future__ import annotations

from dataclasses import dataclass


@dataclass
class OpenRouterConfig:
    model: str = "openai/gpt-4o"
    max_tokens: int = 4096
    temperature: float = 0.3
    api_key: str | None = None
    base_url: str = "https://openrouter.ai/api/v1"
