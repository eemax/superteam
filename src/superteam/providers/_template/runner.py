from __future__ import annotations

from superteam.core.contracts import LoopState


class ExampleProvider:
    def complete(self, system: str, prompt: str, state: LoopState | None = None) -> str:
        return "implement provider-specific logic here"

    def health(self) -> bool:
        return True
