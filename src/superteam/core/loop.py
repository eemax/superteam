from __future__ import annotations

from dataclasses import dataclass, replace
from pathlib import Path
from typing import Literal, Protocol
import re
from textwrap import dedent
import time

import yaml

from .contracts import (
    AUDIT_SECTION_TITLES,
    OUTPUT_INLINE_LIMIT,
    OUTPUT_PREVIEW_LIMIT,
    STATUS_TO_AUDIT_VERDICT,
    IterationRecord,
    LoopState,
    Verdict,
)
from .observe import Observer
from .session import Session


@dataclass
class LoopConfig:
    max_iterations: int = 5
    min_score: float | None = None
    consecutive_passes: int = 1
    on_max_iterations: Literal["fail", "pass_anyway", "raise"] = "fail"
    transient_retries: int = 2
    parse_repair_prompt: bool = True
    stop_on_error: bool = True


class ArtifactStore(Protocol):
    def spill(self, output: str, iteration: int) -> tuple[str, str | None, str]:
        ...

    def load(self, output_ref: str) -> str | None:
        ...


class InlineArtifactStore:
    def spill(self, output: str, iteration: int) -> tuple[str, str | None, str]:
        return output, None, ""

    def load(self, output_ref: str) -> str | None:
        path = Path(output_ref)
        if path.exists():
            return path.read_text(encoding="utf-8")
        return None


class SessionArtifactStore(InlineArtifactStore):
    def __init__(self, session: Session):
        self.session = session

    def spill(self, output: str, iteration: int) -> tuple[str, str | None, str]:
        if len(output) <= OUTPUT_INLINE_LIMIT:
            return output, None, ""

        artifact_path = self.session.artifacts_dir / f"{iteration:03d}.artifact"
        artifact_path.parent.mkdir(parents=True, exist_ok=True)
        artifact_path.write_text(output, encoding="utf-8")
        preview = output[:OUTPUT_PREVIEW_LIMIT] + ("…" if len(output) > OUTPUT_PREVIEW_LIMIT else "")
        inline = f"[artifact spilled to {artifact_path.name} — {len(output):,} chars]\n\n{preview}"
        return inline, str(artifact_path), preview


class _LoopProvider:
    def __init__(self, label: str, provider, observer: Observer, config: LoopConfig):
        self.label = label
        self.provider = provider
        self.observer = observer
        self.config = config
        self.last_tokens: dict[str, int] = {}

    def complete(self, system: str, prompt: str, state: LoopState | None = None) -> str:
        iteration = (state.iteration + 1) if state is not None else 1
        self.observer.emit("step_start", {"step": self.label, "iteration": iteration})

        transient_errors = _transient_exceptions()
        for attempt in range(self.config.transient_retries + 1):
            try:
                result = self.provider.complete(system, prompt, state)
                self.last_tokens = _extract_tokens(self.provider)
                return result
            except transient_errors as exc:
                if attempt >= self.config.transient_retries:
                    raise
                wait_seconds = 2**attempt
                self.observer.emit(
                    "error",
                    {
                        "step": self.label,
                        "type": "transient",
                        "attempt": attempt + 1,
                        "wait": wait_seconds,
                        "message": str(exc),
                    },
                )
                time.sleep(wait_seconds)

        raise RuntimeError("Retry loop exited unexpectedly")

    def health(self) -> bool:
        return self.provider.health()

    def __getattr__(self, name: str):
        return getattr(self.provider, name)


def _load_output_text(state: LoopState, artifact_store: ArtifactStore | None = None) -> str:
    if state.output_ref:
        loaded = artifact_store.load(state.output_ref) if artifact_store else None
        if loaded is None:
            artifact_path = Path(state.output_ref)
            if artifact_path.exists():
                loaded = artifact_path.read_text(encoding="utf-8")
        if loaded is not None:
            return loaded
    return state.output


def build_builder_prompt(state: LoopState, artifact_store: ArtifactStore | None = None) -> str:
    parts = [
        f"## Goal\n{state.goal}\n",
        f"## Plan\n{state.plan}\n",
    ]
    if state.feedback:
        parts.append(f"## Previous audit report\n{state.feedback}\n")
    if state.next_steps:
        next_steps = "\n".join(f"- {step}" for step in state.next_steps)
        parts.append(f"## Required next steps\n{next_steps}\n")
    if state.iteration > 0:
        output_text = _load_output_text(state, artifact_store)
        parts.append(f"## Previous output\n{output_text}\n")
    parts.append("Now execute. Produce your best output.")
    return "\n".join(parts)


def build_evaluator_prompt(state: LoopState, artifact_store: ArtifactStore | None = None) -> str:
    output_text = _load_output_text(state, artifact_store)

    return f"""## Goal
{state.goal}

## Output to evaluate
{output_text}

## Your task
Evaluate the output against the goal as a software engineering audit. Be precise and critical.

{audit_report_format_instructions()}"""


def audit_report_format_instructions() -> str:
    return dedent(
        """\
        Return ONLY the canonical Markdown audit report with YAML frontmatter and no code fences.

        Frontmatter fields:
        - status: pass | fail | retry
        - audit_verdict: PASS | PASS WITH CONDITIONS | FAIL
        - score: numeric 0.0-1.0
        - next_steps: YAML list of concrete action items (must be non-empty for fail or retry)
        - metadata: YAML mapping

        Status mapping:
        - pass -> PASS
        - retry -> PASS WITH CONDITIONS
        - fail -> FAIL

        Required body structure after the frontmatter:
        # Agent Audit
        ## 1. Context
        ## 2. Verdict
        ## 3. Findings Summary
        ## 4. Findings
        ## 5. Recommendations
        ## 6. Audit Details
        ## 7. Scope Exclusions

        The Markdown body is the audit report. Do not return JSON. Do not omit any required section."""
    )


def parse_verdict(
    raw: str,
    config: LoopConfig = LoopConfig(),
    evaluator=None,
    system: str = "",
) -> Verdict:
    def _try_parse(text: str) -> Verdict:
        frontmatter, body = _split_frontmatter(text)
        data = yaml.safe_load(frontmatter)
        if not isinstance(data, dict):
            raise ValueError("Verdict frontmatter must parse to a mapping")
        _validate_audit_body(body)
        verdict = Verdict.from_dict({**data, "feedback": body})
        _validate_verdict(verdict)
        return verdict

    last_error: Exception | None = None

    raw = _strip_code_fences(raw)

    try:
        return _try_parse(raw)
    except (KeyError, TypeError, ValueError, yaml.YAMLError) as exc:
        last_error = exc

    if config.parse_repair_prompt and evaluator is not None:
        raw_preview = raw[:2000]
        repair_prompt = (
            "Your previous response could not be parsed as the required Markdown audit report. "
            "Here is your original response:\n\n"
            f"{raw_preview}\n\n"
            "Please rewrite it into the required canonical Markdown audit format.\n\n"
            f"{audit_report_format_instructions()}"
        )
        repaired = evaluator.complete(system, repair_prompt)
        try:
            return _try_parse(repaired)
        except (KeyError, TypeError, ValueError, yaml.YAMLError) as exc:
            last_error = exc

    if isinstance(last_error, ValueError):
        raise last_error
    if last_error is not None:
        raise ValueError(str(last_error)) from last_error
    raise ValueError(f"Could not parse verdict after all salvage attempts. Raw: {raw[:200]}")


def step_once(
    builder,
    evaluator,
    state: LoopState,
    config: LoopConfig = LoopConfig(),
    builder_system: str = "You are an expert builder. Execute the plan precisely.",
    evaluator_system: str = "You are a rigorous QA evaluator. Return only the canonical Markdown audit report.",
    artifact_store: ArtifactStore | None = None,
) -> tuple[LoopState, Verdict]:
    artifact_store = artifact_store or InlineArtifactStore()

    output_raw = builder.complete(builder_system, build_builder_prompt(state, artifact_store), state)
    output, output_ref, output_preview = _maybe_spill(output_raw, state, artifact_store)
    next_state = replace(
        state,
        output=output,
        output_ref=output_ref,
        output_preview=output_preview,
        iteration=state.iteration + 1,
    )

    raw_verdict = evaluator.complete(
        evaluator_system,
        build_evaluator_prompt(next_state, artifact_store=artifact_store),
        next_state,
    )
    verdict = parse_verdict(raw_verdict, config=config, evaluator=evaluator, system=evaluator_system)
    tokens = _combine_tokens(builder, evaluator)
    record = IterationRecord(
        iteration=next_state.iteration,
        ts_start=0.0,
        ts_end=0.0,
        output_preview=output_preview or output[:OUTPUT_PREVIEW_LIMIT],
        output_ref=output_ref,
        verdict=verdict,
        tokens=tokens,
    )
    next_state = replace(
        next_state,
        feedback=verdict.feedback,
        next_steps=verdict.next_steps,
        history=[*next_state.history, record],
    )
    return next_state, verdict


def run_loop(
    builder,
    evaluator,
    state: LoopState,
    config: LoopConfig = LoopConfig(),
    observer: Observer | None = None,
    session: Session | None = None,
    builder_system: str = "You are an expert builder. Execute the plan precisely.",
    evaluator_system: str = "You are a rigorous QA evaluator. Return only the canonical Markdown audit report.",
) -> LoopState:
    obs = observer or Observer(session=session)
    artifact_store: ArtifactStore = SessionArtifactStore(session) if session else InlineArtifactStore()
    wrapped_builder = _LoopProvider("builder", builder, obs, config)
    wrapped_evaluator = _LoopProvider("evaluator", evaluator, obs, config)
    passes = 0
    last_verdict: Verdict | None = None

    if not state.plan:
        state = replace(state, plan=state.goal)

    while state.iteration < config.max_iterations:
        t0 = time.time()
        try:
            state, verdict = step_once(
                wrapped_builder,
                wrapped_evaluator,
                state,
                config,
                builder_system,
                evaluator_system,
                artifact_store=artifact_store,
            )
        except Exception as exc:
            obs.emit("error", {"step": "step_once", "message": str(exc)})
            if session:
                session.finish("failed")
            if config.stop_on_error:
                raise
            break

        last_verdict = verdict
        stamped = replace(state.history[-1], ts_start=t0, ts_end=time.time())
        state.history[-1] = stamped

        obs.emit(
            "output",
            {
                "iteration": state.iteration,
                "output_preview": state.output_preview or state.output[:OUTPUT_PREVIEW_LIMIT],
                "spilled": state.output_ref is not None,
            },
        )
        verdict_payload = {
            "iteration": state.iteration,
            "status": verdict.status,
            "audit_verdict": verdict.audit_verdict,
            "score": verdict.score,
        }
        summary = _summarize_audit_report(verdict.feedback)
        next_steps = _summarize_next_steps(verdict.next_steps)
        if summary:
            verdict_payload["summary"] = summary
        if next_steps:
            verdict_payload["next_steps"] = next_steps
        obs.emit("verdict", verdict_payload)

        if session:
            session.checkpoint(state, verdict)

        score_ok = config.min_score is None or verdict.score >= config.min_score
        if verdict.status == "pass" and score_ok:
            passes += 1
            if passes >= config.consecutive_passes:
                obs.emit("loop_end", {"reason": "pass", "iterations": state.iteration})
                if session:
                    session.finish("done", score=verdict.score)
                break
        else:
            passes = 0
    else:
        obs.emit("loop_end", {"reason": "max_iterations", "iterations": state.iteration})
        if session:
            status = "failed" if config.on_max_iterations == "fail" else "done"
            score = last_verdict.score if last_verdict else None
            session.finish(status, score=score)
        if config.on_max_iterations == "raise":
            raise RuntimeError(f"Loop hit max_iterations ({config.max_iterations})")

    return state


def _maybe_spill(
    output: str,
    state: LoopState,
    artifact_store: ArtifactStore,
) -> tuple[str, str | None, str]:
    if len(output) <= OUTPUT_INLINE_LIMIT:
        return output, None, ""
    return artifact_store.spill(output, state.iteration + 1)


def _combine_tokens(builder, evaluator) -> dict[str, dict[str, int]]:
    combined: dict[str, dict[str, int]] = {}
    for label, provider in (("builder", builder), ("evaluator", evaluator)):
        usage = _extract_tokens(provider)
        if usage:
            combined[label] = usage
    return combined


def _extract_tokens(provider) -> dict[str, int]:
    usage = getattr(provider, "last_tokens", None)
    if callable(usage):
        usage = usage()
    if isinstance(usage, dict):
        return {
            key: int(value)
            for key, value in usage.items()
            if isinstance(value, int) and not isinstance(value, bool)
        }
    return {}


def _transient_exceptions() -> tuple[type[BaseException], ...]:
    exceptions: list[type[BaseException]] = [TimeoutError, ConnectionError]
    try:
        import httpx

        exceptions.extend([httpx.TimeoutException, httpx.NetworkError])
    except ImportError:
        pass

    try:
        from anthropic import APIConnectionError, APITimeoutError, InternalServerError, RateLimitError

        exceptions.extend([APIConnectionError, APITimeoutError, InternalServerError, RateLimitError])
    except ImportError:
        pass

    return tuple(dict.fromkeys(exceptions))


def _strip_code_fences(text: str) -> str:
    stripped = text.strip()
    if stripped.startswith("```"):
        first_nl = stripped.index("\n")
        stripped = stripped[first_nl + 1 :]
    if stripped.endswith("```"):
        stripped = stripped[: -3]
    return stripped.strip()


def _split_frontmatter(raw: str) -> tuple[str, str]:
    text = raw.strip()
    if not text.startswith("---"):
        raise ValueError("Verdict must start with YAML frontmatter")

    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        raise ValueError("Verdict must open with a frontmatter delimiter")

    for index in range(1, len(lines)):
        if lines[index].strip() == "---":
            frontmatter = "\n".join(lines[1:index]).strip()
            body = "\n".join(lines[index + 1 :]).strip()
            if not frontmatter:
                raise ValueError("Verdict frontmatter is empty")
            if not body:
                raise ValueError("Verdict body is empty")
            return frontmatter, body

    raise ValueError("Verdict frontmatter is missing a closing delimiter")


def _validate_verdict(verdict: Verdict) -> None:
    if verdict.status not in STATUS_TO_AUDIT_VERDICT:
        raise ValueError(f"Unsupported verdict status: {verdict.status}")
    expected_audit_verdict = STATUS_TO_AUDIT_VERDICT[verdict.status]
    if verdict.audit_verdict != expected_audit_verdict:
        raise ValueError(
            f"status={verdict.status!r} requires audit_verdict={expected_audit_verdict!r}, "
            f"got {verdict.audit_verdict!r}"
        )
    if not isinstance(verdict.score, (int, float)):
        raise ValueError("Verdict score must be numeric")
    if not isinstance(verdict.metadata, dict):
        raise ValueError("Verdict metadata must be a mapping")
    if not isinstance(verdict.next_steps, list) or any(not isinstance(step, str) or not step.strip() for step in verdict.next_steps):
        raise ValueError("Verdict next_steps must be a list of non-empty strings")
    if verdict.status != "pass" and not verdict.next_steps:
        raise ValueError("Verdict next_steps must be non-empty for fail or retry")


def _validate_audit_body(body: str) -> None:
    titles = [
        re.sub(r"^\d+\.\s+", "", match.group(1)).strip()
        for match in re.finditer(r"^##\s+(.+?)\s*$", body, re.MULTILINE)
    ]
    if titles != list(AUDIT_SECTION_TITLES):
        raise ValueError(
            "Verdict body must contain the required sections in order: "
            + ", ".join(AUDIT_SECTION_TITLES)
        )


def _summarize_audit_report(body: str, limit: int = 160) -> str:
    for raw_line in body.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or line.startswith("-") or line.startswith(">"):
            continue
        if len(line) <= limit:
            return line
        return line[: limit - 1] + "…"
    return ""


def _summarize_next_steps(next_steps: list[str], limit: int = 2) -> str:
    if not next_steps:
        return ""
    return "; ".join(next_steps[:limit])
