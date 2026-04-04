from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


@dataclass
class ClaudeCodeConfig:
    model: str | None = None
    working_dir: str | None = None
    max_turns: int | None = None
    timeout: int = 300
    allowed_tools: list[str] | None = None
    env: dict[str, str] | None = None
    bare: bool = True
    permission_mode: Literal["default", "plan", "bypassPermissions"] | None = None
