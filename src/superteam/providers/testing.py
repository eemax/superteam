from __future__ import annotations

from dataclasses import dataclass, field

from superteam.core.contracts import LoopState, Verdict


@dataclass
class StaticBuilderConfig:
    outputs: list[str] = field(default_factory=lambda: ["builder output"])


@dataclass
class StaticEvaluatorConfig:
    responses: list[dict] = field(
        default_factory=lambda: [
            {
                "status": "pass",
                "audit_verdict": "PASS",
                "score": 1.0,
                "next_steps": [],
                "metadata": {},
                "feedback": "# Agent Audit\n\n## 1. Context\nDefault test audit.\n\n## 2. Verdict\n**PASS**\n\n**Rationale:** Default pass.\n\n**Confidence:** High\n\n## 3. Findings Summary\n- **P1 - Critical:** 0\n- **P2 - Major:** 0\n- **P3 - Minor:** 0\n\n## 4. Findings\nNo open findings.\n\n## 5. Recommendations\n### Before Ship\n- None.\n\n### Before Next Milestone\n- None.\n\n### Longer-Term Improvements\n- None.\n\n## 6. Audit Details\n- **Files reviewed:** []\n- **Tests run:** []\n- **Results:** 0 passed, 0 failed, 0 skipped\n- **Tools used:** [\"static review\"]\n- **Method:** static review\n- **Environment:** test harness\n- **Reference:** test fixture\n- **Audited by:** fake_evaluator\n- **Timestamp:** 2026-03-31T00:00:00+07:00\n\n## 7. Scope Exclusions\n- None.",
            }
        ]
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
        response = _render_response(self.config.responses[index])
        self.last_tokens = {"input": len(prompt), "output": len(response), "total": len(prompt) + len(response)}
        return response

    def health(self) -> bool:
        return True


def _render_response(data: dict) -> str:
    feedback = data["feedback"]
    if "## 1. Context" not in feedback:
        feedback = _default_audit_body(
            summary=feedback,
            audit_verdict=data["audit_verdict"],
            next_steps=data["next_steps"],
        )
    verdict = Verdict.from_dict({**data, "feedback": feedback})
    return verdict.to_markdown()


def _default_audit_body(summary: str, audit_verdict: str, next_steps: list[str]) -> str:
    next_step_lines = "\n".join(f"- {step}" for step in next_steps) if next_steps else "- None."
    return (
        "# Agent Audit\n\n"
        "## 1. Context\n"
        f"{summary}\n\n"
        "## 2. Verdict\n"
        f"**{audit_verdict}**\n\n"
        f"**Rationale:** {summary}\n\n"
        "**Confidence:** Medium\n"
        "Synthetic deterministic audit response.\n\n"
        "## 3. Findings Summary\n"
        "- **P1 - Critical:** 0\n"
        "- **P2 - Major:** 0\n"
        "- **P3 - Minor:** 0\n\n"
        "## 4. Findings\n"
        "No detailed findings recorded in the static evaluator.\n\n"
        "## 5. Recommendations\n"
        "### Before Ship\n"
        f"{next_step_lines}\n\n"
        "### Before Next Milestone\n"
        "- None.\n\n"
        "### Longer-Term Improvements\n"
        "- None.\n\n"
        "## 6. Audit Details\n"
        "- **Files reviewed:** []\n"
        "- **Tests run:** []\n"
        "- **Results:** 0 passed, 0 failed, 0 skipped\n"
        "- **Tools used:** [\"static review\"]\n"
        "- **Method:** static review\n"
        "- **Environment:** static evaluator\n"
        "- **Reference:** test fixture\n"
        "- **Audited by:** fake_evaluator\n"
        "- **Timestamp:** 2026-03-31T00:00:00+07:00\n\n"
        "## 7. Scope Exclusions\n"
        "- None."
    )
