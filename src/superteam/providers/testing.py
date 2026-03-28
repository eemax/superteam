from __future__ import annotations

from dataclasses import dataclass, field
import json

from superteam.core.contracts import LoopState


@dataclass
class StaticBuilderConfig:
    outputs: list[str] = field(default_factory=lambda: ["builder output"])


@dataclass
class StaticEvaluatorConfig:
    responses: list[dict] = field(
        default_factory=lambda: [{"status": "pass", "feedback": "ok", "score": 1.0}]
    )


class StaticBuilderProvider:
    def __init__(self, config: StaticBuilderConfig = StaticBuilderConfig()):
        self.config = config
        self.calls = 0
        self.last_tokens: dict[str, int] = {}

    def complete(self, system: str, prompt: str, state: LoopState | None = None) -> str:
        index = min(self.calls, len(self.config.outputs) - 1)
        self.calls += 1
        output = self.config.outputs[index]
        self.last_tokens = {"input": len(prompt), "output": len(output), "total": len(prompt) + len(output)}
        return output

    def health(self) -> bool:
        return True


class StaticEvaluatorProvider:
    def __init__(self, config: StaticEvaluatorConfig = StaticEvaluatorConfig()):
        self.config = config
        self.calls = 0
        self.last_tokens: dict[str, int] = {}

    def complete(self, system: str, prompt: str, state: LoopState | None = None) -> str:
        index = min(self.calls, len(self.config.responses) - 1)
        self.calls += 1
        response = json.dumps(self.config.responses[index])
        self.last_tokens = {"input": len(prompt), "output": len(response), "total": len(prompt) + len(response)}
        return response

    def health(self) -> bool:
        return True
