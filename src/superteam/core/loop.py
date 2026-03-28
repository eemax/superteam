from __future__ import annotations

from dataclasses import dataclass, replace
from pathlib import Path
from typing import Literal, Protocol
import json
import re
import time

from .contracts import IterationRecord, LoopState, OUTPUT_INLINE_LIMIT, OUTPUT_PREVIEW_LIMIT, Verdict
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
        parts.append(f"## Feedback from previous attempt\n{state.feedback}\n")
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
Evaluate the output against the goal. Be precise and critical.
Respond ONLY as JSON:
{{
  "status": "pass" | "fail" | "retry",
  "feedback": "specific, actionable feedback for the builder",
  "score": 0.0-1.0
}}"""


def _salvage_json(raw: str) -> str:
    cleaned = re.sub(r"```(?:json)?\s*", "", raw).strip()
    cleaned = cleaned.replace("```", "").strip()
    match = re.search(r"\{.*\}", cleaned, re.DOTALL)
    return match.group(0) if match else cleaned


def parse_verdict(
    raw: str,
    config: LoopConfig = LoopConfig(),
    evaluator=None,
    system: str = "",
) -> Verdict:
    def _try_parse(text: str) -> Verdict:
        data = json.loads(text)
        verdict = Verdict.from_dict(data)
        if verdict.status not in {"pass", "fail", "retry"}:
            raise ValueError(f"Unsupported verdict status: {verdict.status}")
        return verdict

    for attempt in (raw, _salvage_json(raw)):
        try:
            return _try_parse(attempt)
        except (json.JSONDecodeError, KeyError, ValueError, TypeError):
            continue

    if config.parse_repair_prompt and evaluator is not None:
        raw_preview = raw[:2000]
        repair_prompt = (
            "Your previous response could not be parsed as JSON. "
            "Here is your original response:\n\n"
            f"{raw_preview}\n\n"
            "Please fix the above into a valid JSON object "
            "with keys status, feedback, and score.\n"
            '{"status": "pass"|"fail"|"retry", "feedback": "...", "score": 0.0}'
        )
        repaired = evaluator.complete(system, repair_prompt)
        try:
            return _try_parse(_salvage_json(repaired))
        except (json.JSONDecodeError, KeyError, ValueError, TypeError):
            pass

    raise ValueError(f"Could not parse verdict after all salvage attempts. Raw: {raw[:200]}")


def step_once(
    builder,
    evaluator,
    state: LoopState,
    config: LoopConfig = LoopConfig(),
    builder_system: str = "You are an expert builder. Execute the plan precisely.",
    evaluator_system: str = "You are a rigorous QA evaluator. Return JSON only.",
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
    evaluator_system: str = "You are a rigorous QA evaluator. Return JSON only.",
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
        obs.emit(
            "verdict",
            {
                "iteration": state.iteration,
                "status": verdict.status,
                "score": verdict.score,
                "feedback": verdict.feedback,
            },
        )

        if session:
            session.checkpoint(state, verdict)

        score_ok = (
            verdict.score is not None
            and config.min_score is not None
            and verdict.score >= config.min_score
        )
        if verdict.status == "pass" or score_ok:
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
