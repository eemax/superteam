from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Literal
import json
import time
import uuid


OUTPUT_INLINE_LIMIT = 8_000
OUTPUT_PREVIEW_LIMIT = 300


@dataclass
class Verdict:
    status: Literal["pass", "fail", "retry"]
    feedback: str
    score: float | None = None
    next_step: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Verdict":
        return cls(
            status=data["status"],
            feedback=data.get("feedback", ""),
            score=data.get("score"),
            next_step=data.get("next_step"),
            metadata=data.get("metadata", {}),
        )


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
class LoopState:
    session_id: str
    goal: str
    plan: str
    iteration: int = 0
    output: str = ""
    output_ref: str | None = None
    output_preview: str = ""
    feedback: str | None = None
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
    builder_provider: str
    eval_provider: str
    status: Literal["running", "done", "failed", "paused"]
    created_at: float = field(default_factory=time.time)
    ended_at: float | None = None
    iterations: int = 0
    final_score: float | None = None

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "SessionMeta":
        return cls(**data)


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
