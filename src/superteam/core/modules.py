from __future__ import annotations

from typing import Literal, Protocol, runtime_checkable

from .contracts import LoopState


ModuleRole = Literal["builder", "auditor"]


@runtime_checkable
class Module(Protocol):
    def run(
        self,
        role: ModuleRole,
        system: str,
        prompt: str,
        state: LoopState | None = None,
        cwd: str | None = None,
    ) -> str:
        ...

    def health(self) -> bool:
        ...

    def capabilities(self) -> set[ModuleRole] | tuple[ModuleRole, ...]:
        ...
