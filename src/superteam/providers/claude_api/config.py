from __future__ import annotations

from dataclasses import dataclass


@dataclass
class ClaudeAPIConfig:
    model: str = "claude-sonnet-4-6"
    max_tokens: int = 4096
    temperature: float = 0.2
    api_key: str | None = None
