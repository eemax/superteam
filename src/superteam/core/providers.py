from __future__ import annotations

from typing import Protocol, runtime_checkable

from .contracts import LoopState


@runtime_checkable
class Provider(Protocol):
    def complete(self, system: str, prompt: str, state: LoopState | None = None) -> str:
        ...

    def health(self) -> bool:
        ...
