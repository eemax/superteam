from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class CodexConfig:
    model: str | None = None
    working_dir: str | None = None
    timeout: int = 600
    profile: str | None = None
    skip_git_repo_check: bool = False
    extra_args: list[str] = field(default_factory=list)
