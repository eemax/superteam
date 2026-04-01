from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Literal
import json
import time
import uuid

import yaml


OUTPUT_INLINE_LIMIT = 8_000
OUTPUT_PREVIEW_LIMIT = 300
AUDIT_SECTION_TITLES = (
    "Context",
    "Verdict",
    "Findings Summary",
    "Findings",
    "Recommendations",
    "Audit Details",
    "Scope Exclusions",
)
STATUS_TO_AUDIT_VERDICT = {
    "pass": "PASS",
    "retry": "PASS WITH CONDITIONS",
    "fail": "FAIL",
}


@dataclass
class Verdict:
    status: Literal["pass", "fail", "retry"]
    audit_verdict: Literal["PASS", "PASS WITH CONDITIONS", "FAIL"]
    feedback: str
    score: float
    next_steps: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Verdict":
        return cls(
            status=data["status"],
            audit_verdict=data["audit_verdict"],
            feedback=data["feedback"],
            score=float(data["score"]),
            next_steps=list(data["next_steps"]),
            metadata=dict(data["metadata"]),
        )

    def to_markdown(self) -> str:
        frontmatter = yaml.safe_dump(
            {
                "status": self.status,
                "audit_verdict": self.audit_verdict,
                "score": self.score,
                "next_steps": self.next_steps,
                "metadata": self.metadata,
            },
            sort_keys=False,
            allow_unicode=False,
        ).strip()
        body = self.feedback.strip()
        return f"---\n{frontmatter}\n---\n\n{body}\n"


@dataclass
class IterationRecord:
    iteration: int
    ts_start: float
    ts_end: float
    output_preview: str
    output_ref: str | None
    verdict: Verdict
    tokens: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "IterationRecord":
        return cls(
            iteration=data["iteration"],
            ts_start=data["ts_start"],
            ts_end=data["ts_end"],
            output_preview=data.get("output_preview", ""),
            output_ref=data.get("output_ref"),
            verdict=Verdict.from_dict(data["verdict"]),
            tokens=data.get("tokens", {}),
        )


@dataclass
class InvocationRecord:
    index: int
    iteration: int
    module: str
    role: Literal["builder", "auditor"]
    attempt: int
    started_at: float
    ended_at: float
    duration_seconds: float
    cwd: str | None
    system: str = ""
    system_ref: str | None = None
    prompt: str = ""
    prompt_ref: str | None = None
    output: str = ""
    output_ref: str | None = None
    error: str | None = None

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "InvocationRecord":
        return cls(
            index=data["index"],
            iteration=data["iteration"],
            module=data["module"],
            role=data["role"],
            attempt=data.get("attempt", 1),
            started_at=data["started_at"],
            ended_at=data["ended_at"],
            duration_seconds=data["duration_seconds"],
            cwd=data.get("cwd"),
            system=data.get("system", ""),
            system_ref=data.get("system_ref"),
            prompt=data.get("prompt", ""),
            prompt_ref=data.get("prompt_ref"),
            output=data.get("output", ""),
            output_ref=data.get("output_ref"),
            error=data.get("error"),
        )


@dataclass
class LoopState:
    session_id: str
    goal: str
    plan: str
    iteration: int = 0
    output: str = ""
    output_ref: str | None = None
    output_preview: str = ""
    feedback: str | None = None
    next_steps: list[str] = field(default_factory=list)
    context: dict[str, Any] = field(default_factory=dict)
    history: list[IterationRecord] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "LoopState":
        return cls(
            session_id=data["session_id"],
            goal=data["goal"],
            plan=data.get("plan", ""),
            iteration=data.get("iteration", 0),
            output=data.get("output", ""),
            output_ref=data.get("output_ref"),
            output_preview=data.get("output_preview", ""),
            feedback=data.get("feedback"),
            next_steps=data.get("next_steps", []),
            context=data.get("context", {}),
            history=[IterationRecord.from_dict(item) for item in data.get("history", [])],
        )

    @classmethod
    def from_json(cls, raw: str) -> "LoopState":
        return cls.from_dict(json.loads(raw))


@dataclass
class SessionMeta:
    session_id: str
    pipeline: str | None
    builder_module: str
    auditor_module: str
    status: Literal["running", "done", "failed", "paused"]
    created_at: float = field(default_factory=time.time)
    ended_at: float | None = None
    iterations: int = 0
    final_score: float | None = None

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "SessionMeta":
        return cls(
            session_id=data["session_id"],
            pipeline=data.get("pipeline"),
            builder_module=data["builder_module"],
            auditor_module=data["auditor_module"],
            status=data["status"],
            created_at=data.get("created_at", 0.0),
            ended_at=data.get("ended_at"),
            iterations=data.get("iterations", 0),
            final_score=data.get("final_score"),
        )


@dataclass
class Event:
    ts: float
    event: str
    payload: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {"ts": self.ts, "event": self.event, **self.payload}

    def to_jsonl(self) -> str:
        return json.dumps(self.to_dict())

    @classmethod
    def from_jsonl(cls, raw: str) -> "Event":
        data = json.loads(raw)
        payload = {key: value for key, value in data.items() if key not in {"ts", "event"}}
        return cls(ts=data["ts"], event=data["event"], payload=payload)


def new_session_id() -> str:
    return f"st-{uuid.uuid4().hex[:8]}"
