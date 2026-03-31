from __future__ import annotations

from dataclasses import asdict, replace
from pathlib import Path
from tempfile import NamedTemporaryFile
import json
import os
import time

from .contracts import InvocationRecord, LoopState, SessionMeta, Verdict, new_session_id


SUPERTEAM_HOME_ENV = "SUPERTEAM_HOME"
TERMINAL_SESSION_STATUSES = {"done", "failed", "paused"}


def superteam_home() -> Path:
    raw = os.environ.get(SUPERTEAM_HOME_ENV)
    if raw:
        return Path(raw).expanduser()
    return Path.home() / ".superteam"


def sessions_dir() -> Path:
    return superteam_home() / "sessions"


def _write_text_atomic(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with NamedTemporaryFile("w", encoding="utf-8", dir=path.parent, delete=False) as handle:
        handle.write(text)
        tmp_path = Path(handle.name)
    tmp_path.replace(path)


class Session:
    def __init__(
        self,
        session_id: str | None = None,
        builder_module: str = "unknown",
        auditor_module: str = "unknown",
        pipeline: str | None = None,
        *,
        create: bool = True,
    ):
        self.id = session_id or new_session_id()
        self.dir = sessions_dir() / self.id
        self.events_path = self.dir / "events.jsonl"
        self.meta_path = self.dir / "meta.json"
        self.state_path = self.dir / "state.json"
        self.iterations_dir = self.dir / "iterations"
        self.artifacts_dir = self.dir / "artifacts"
        self.invocations_dir = self.dir / "invocations"
        self.workspace_dir = self.dir / "workspace"
        self.run_pid_path = self.dir / "run.pid"

        if create:
            self._ensure_layout()
            if not self.meta_path.exists():
                meta = SessionMeta(
                    session_id=self.id,
                    pipeline=pipeline,
                    builder_module=builder_module,
                    auditor_module=auditor_module,
                    status="running",
                )
                self._write_meta(meta)
        else:
            if not self.dir.exists() or not self.meta_path.exists():
                raise FileNotFoundError(f"Session '{self.id}' does not exist")

    @classmethod
    def create(
        cls,
        session_id: str | None = None,
        builder_module: str = "unknown",
        auditor_module: str = "unknown",
        pipeline: str | None = None,
    ) -> "Session":
        return cls(
            session_id=session_id,
            builder_module=builder_module,
            auditor_module=auditor_module,
            pipeline=pipeline,
            create=True,
        )

    @classmethod
    def open(cls, session_id: str) -> "Session":
        return cls(session_id=session_id, create=False)

    @classmethod
    def list_all(cls, status: str | None = None) -> list["Session"]:
        root = sessions_dir()
        if not root.exists():
            return []
        sessions: list[Session] = []
        for entry in sorted(root.iterdir()):
            if not entry.is_dir():
                continue
            try:
                session = cls.open(entry.name)
            except FileNotFoundError:
                continue
            if status is None or session.load_meta().status == status:
                sessions.append(session)
        return sessions

    def _ensure_layout(self) -> None:
        self.iterations_dir.mkdir(parents=True, exist_ok=True)
        self.artifacts_dir.mkdir(parents=True, exist_ok=True)
        self.invocations_dir.mkdir(parents=True, exist_ok=True)
        self.workspace_dir.mkdir(parents=True, exist_ok=True)

    def _write_meta(self, meta: SessionMeta) -> None:
        _write_text_atomic(self.meta_path, json.dumps(asdict(meta), indent=2))

    def load_meta(self) -> SessionMeta:
        return SessionMeta.from_dict(json.loads(self.meta_path.read_text(encoding="utf-8")))

    def update_meta(self, **kwargs) -> SessionMeta:
        meta = replace(self.load_meta(), **kwargs)
        self._write_meta(meta)
        return meta

    def finish(self, status: str, score: float | None = None) -> None:
        self.update_meta(status=status, ended_at=time.time(), final_score=score)

    def checkpoint(self, state: LoopState, verdict: Verdict) -> None:
        iteration = state.iteration
        _write_text_atomic(self.iterations_dir / f"{iteration:03d}.json", state.to_json())
        _write_text_atomic(
            self.iterations_dir / f"{iteration:03d}.verdict.json",
            json.dumps(asdict(verdict), indent=2),
        )
        _write_text_atomic(self.state_path, state.to_json())
        self.update_meta(iterations=iteration)

    def record_invocation(self, record: InvocationRecord) -> InvocationRecord:
        index = self.next_invocation_index()
        system, system_ref = self._inline_or_spill_invocation_text(index, "system", record.system)
        prompt, prompt_ref = self._inline_or_spill_invocation_text(index, "prompt", record.prompt)
        output, output_ref = self._inline_or_spill_invocation_text(index, "output", record.output)
        stored = replace(
            record,
            index=index,
            system=system,
            system_ref=system_ref,
            prompt=prompt,
            prompt_ref=prompt_ref,
            output=output,
            output_ref=output_ref,
        )
        _write_text_atomic(
            self.invocations_dir / f"{stored.index:04d}.json",
            json.dumps(asdict(stored), indent=2),
        )
        return stored

    def list_invocations(self) -> list[InvocationRecord]:
        if not self.invocations_dir.exists():
            return []
        records: list[InvocationRecord] = []
        for path in sorted(self.invocations_dir.glob("*.json")):
            records.append(InvocationRecord.from_dict(json.loads(path.read_text(encoding="utf-8"))))
        return records

    def load_state(self) -> LoopState:
        return LoopState.from_json(self.state_path.read_text(encoding="utf-8"))

    def load_state_optional(self) -> LoopState | None:
        if not self.state_path.exists():
            return None
        return self.load_state()

    def append_event(self, line: str) -> None:
        self.events_path.parent.mkdir(parents=True, exist_ok=True)
        with self.events_path.open("a", encoding="utf-8") as handle:
            handle.write(line + "\n")

    def write_run_pid(self, pid: int) -> None:
        _write_text_atomic(self.run_pid_path, f"{pid}\n")

    def load_run_pid(self) -> int | None:
        if not self.run_pid_path.exists():
            return None
        try:
            return int(self.run_pid_path.read_text(encoding="utf-8").strip())
        except ValueError:
            return None

    def resolve_output_text(self, state: LoopState | None = None) -> str:
        state = state or self.load_state()
        if state.output_ref:
            path = Path(state.output_ref)
            if path.exists():
                return path.read_text(encoding="utf-8")
        return state.output

    def next_invocation_index(self) -> int:
        if not self.invocations_dir.exists():
            return 1
        return len(list(self.invocations_dir.glob("*.json"))) + 1

    def _inline_or_spill_invocation_text(
        self,
        index: int,
        field_name: str,
        text: str,
        inline_limit: int = 8_000,
    ) -> tuple[str, str | None]:
        if len(text) <= inline_limit:
            return text, None
        artifact_path = self.artifacts_dir / f"invocation-{index:04d}-{field_name}.txt"
        artifact_path.parent.mkdir(parents=True, exist_ok=True)
        artifact_path.write_text(text, encoding="utf-8")
        preview = text[:300] + ("…" if len(text) > 300 else "")
        inline = f"[artifact spilled to {artifact_path.name}]\n\n{preview}"
        return inline, str(artifact_path)
