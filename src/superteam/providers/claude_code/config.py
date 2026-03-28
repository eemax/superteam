from __future__ import annotations

from dataclasses import dataclass


@dataclass
class ClaudeCodeConfig:
    model: str = "claude-opus-4-1"
    working_dir: str | None = None
    max_turns: int | None = None
    timeout: int = 300
    allowed_tools: list[str] | None = None
    env: dict[str, str] | None = None
    bare: bool = True
    permission_mode: str | None = None
