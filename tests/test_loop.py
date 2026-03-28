from __future__ import annotations

from pathlib import Path
import json

import pytest

from superteam.core.contracts import LoopState, OUTPUT_INLINE_LIMIT, Verdict
from superteam.core.loop import LoopConfig, SessionArtifactStore, parse_verdict, run_loop, step_once
from superteam.core.observe import Observer
from superteam.core.session import Session


class SequenceBuilder:
    def __init__(self, outputs: list[str]):
        self.outputs = outputs
        self.calls = 0
        self.last_tokens: dict[str, int] = {}

    def complete(self, system: str, prompt: str, state: LoopState | None = None) -> str:
        index = min(self.calls, len(self.outputs) - 1)
        self.calls += 1
        output = self.outputs[index]
        self.last_tokens = {"input": len(prompt), "output": len(output), "total": len(prompt) + len(output)}
        return output

    def health(self) -> bool:
        return True


class RecordingEvaluator:
    def __init__(self, response: str):
        self.response = response
        self.prompts: list[str] = []
        self.calls = 0
        self.last_tokens: dict[str, int] = {}

    def complete(self, system: str, prompt: str, state: LoopState | None = None) -> str:
        self.prompts.append(prompt)
        self.calls += 1
        self.last_tokens = {"input": len(prompt), "output": len(self.response), "total": len(prompt) + len(self.response)}
        return self.response

    def health(self) -> bool:
        return True


class RepairEvaluator:
    def __init__(self):
        self.calls = 0

    def complete(self, system: str, prompt: str, state: LoopState | None = None) -> str:
        self.calls += 1
        return json.dumps({"status": "retry", "feedback": "fix json", "score": 0.2})

    def health(self) -> bool:
        return True


class FlakyBuilder:
    def __init__(self, failures: int, output: str):
        self.failures = failures
        self.output = output
        self.calls = 0
        self.last_tokens: dict[str, int] = {}

    def complete(self, system: str, prompt: str, state: LoopState | None = None) -> str:
        self.calls += 1
        if self.calls <= self.failures:
            raise TimeoutError("temporary timeout")
        self.last_tokens = {"input": len(prompt), "output": len(self.output), "total": len(prompt) + len(self.output)}
        return self.output

    def health(self) -> bool:
        return True


def test_step_once_spills_large_output_and_evaluator_reads_full_artifact():
    session = Session.create(builder_provider="fake_builder", eval_provider="fake_evaluator", pipeline="test")
    builder_output = "A" * (OUTPUT_INLINE_LIMIT + 250)
    builder = SequenceBuilder([builder_output])
    evaluator = RecordingEvaluator('{"status": "pass", "feedback": "ok", "score": 1.0}')
    state = LoopState(session_id=session.id, goal="Review this", plan="Do it")

    next_state, verdict = step_once(
        builder,
        evaluator,
        state,
        artifact_store=SessionArtifactStore(session),
    )

    assert verdict.status == "pass"
    assert next_state.output_ref is not None
    assert Path(next_state.output_ref).read_text(encoding="utf-8") == builder_output
    assert builder_output in evaluator.prompts[0]
    assert next_state.output.startswith("[artifact spilled to")
    assert next_state.history[-1].tokens["builder"]["output"] == len(builder_output)


def test_parse_verdict_repairs_invalid_json_once():
    evaluator = RepairEvaluator()

    verdict = parse_verdict(
        "not json at all",
        config=LoopConfig(parse_repair_prompt=True),
        evaluator=evaluator,
        system="Return JSON only.",
    )

    assert verdict == Verdict(status="retry", feedback="fix json", score=0.2)
    assert evaluator.calls == 1


def test_run_loop_retries_transient_errors_and_succeeds():
    builder = FlakyBuilder(failures=2, output="stable output")
    evaluator = RecordingEvaluator('{"status": "pass", "feedback": "great", "score": 0.99}')
    state = LoopState(session_id="st-retry", goal="goal", plan="plan")

    final = run_loop(
        builder,
        evaluator,
        state,
        config=LoopConfig(max_iterations=1, transient_retries=2),
        observer=Observer(),
    )

    assert final.iteration == 1
    assert builder.calls == 3
    assert final.history[-1].verdict.status == "pass"


def test_run_loop_uses_min_score_as_exit_condition():
    builder = SequenceBuilder(["draft"])
    evaluator = RecordingEvaluator('{"status": "retry", "feedback": "almost", "score": 0.95}')
    session = Session.create(builder_provider="fake_builder", eval_provider="fake_evaluator", pipeline="score")
    state = LoopState(session_id=session.id, goal="goal", plan="plan")

    final = run_loop(
        builder,
        evaluator,
        state,
        config=LoopConfig(max_iterations=3, min_score=0.9),
        observer=Observer(session=session),
        session=session,
    )

    assert final.iteration == 1
    assert session.load_meta().status == "done"


def test_run_loop_marks_session_failed_on_max_iterations():
    builder = SequenceBuilder(["draft one", "draft two"])
    evaluator = RecordingEvaluator('{"status": "fail", "feedback": "still wrong", "score": 0.1}')
    session = Session.create(builder_provider="fake_builder", eval_provider="fake_evaluator", pipeline="max")
    state = LoopState(session_id=session.id, goal="goal", plan="plan")

    final = run_loop(
        builder,
        evaluator,
        state,
        config=LoopConfig(max_iterations=2, on_max_iterations="fail"),
        observer=Observer(session=session),
        session=session,
    )

    assert final.iteration == 2
    assert session.load_meta().status == "failed"


def test_builder_prompt_loads_full_artifact_when_spilled():
    """Builder should see the full previous artifact, not just the spill marker."""
    from superteam.core.loop import build_builder_prompt, InlineArtifactStore

    large_output = "B" * 10_000
    session = Session.create(builder_provider="test", eval_provider="test", pipeline="test")
    artifact_store = SessionArtifactStore(session)

    inline, ref, preview = artifact_store.spill(large_output, 1)
    state = LoopState(
        session_id=session.id,
        goal="goal",
        plan="plan",
        iteration=1,
        output=inline,
        output_ref=ref,
    )

    prompt = build_builder_prompt(state, artifact_store)
    assert large_output in prompt
    assert "[artifact spilled" not in prompt.split("## Previous output")[1]


def test_both_prompts_see_same_full_artifact():
    """Builder and evaluator should both see the full artifact text."""
    from superteam.core.loop import build_builder_prompt, build_evaluator_prompt

    large_output = "C" * 10_000
    session = Session.create(builder_provider="test", eval_provider="test", pipeline="test")
    artifact_store = SessionArtifactStore(session)

    inline, ref, preview = artifact_store.spill(large_output, 1)
    state = LoopState(
        session_id=session.id,
        goal="goal",
        plan="plan",
        iteration=1,
        output=inline,
        output_ref=ref,
    )

    builder_prompt = build_builder_prompt(state, artifact_store)
    evaluator_prompt = build_evaluator_prompt(state, artifact_store)
    assert large_output in builder_prompt
    assert large_output in evaluator_prompt


def test_run_loop_token_capture_in_history():
    builder = SequenceBuilder(["output"])
    evaluator = RecordingEvaluator('{"status": "pass", "feedback": "ok", "score": 1.0}')
    state = LoopState(session_id="st-tokens", goal="goal", plan="plan")

    final = run_loop(
        builder, evaluator, state,
        config=LoopConfig(max_iterations=1),
        observer=Observer(),
    )

    tokens = final.history[-1].tokens
    assert "builder" in tokens
    assert "evaluator" in tokens
    assert tokens["builder"]["output"] > 0


def test_parse_verdict_repair_prompt_includes_original_response():
    class CapturingEvaluator:
        def __init__(self):
            self.last_prompt = ""

        def complete(self, system: str, prompt: str, state: LoopState | None = None) -> str:
            self.last_prompt = prompt
            return '{"status": "pass", "feedback": "fixed", "score": 0.8}'

    evaluator = CapturingEvaluator()
    raw = "This is not JSON but has some structure {broken"
    verdict = parse_verdict(
        raw,
        config=LoopConfig(parse_repair_prompt=True),
        evaluator=evaluator,
        system="Return JSON only.",
    )
    assert raw in evaluator.last_prompt
    assert verdict.status == "pass"


def test_run_loop_stop_on_error_false_finishes_session():
    class FailingBuilder:
        last_tokens: dict[str, int] = {}

        def complete(self, system: str, prompt: str, state: LoopState | None = None) -> str:
            raise RuntimeError("boom")

        def health(self) -> bool:
            return True

    evaluator = RecordingEvaluator('{"status":"pass","feedback":"ok","score":1.0}')
    session = Session.create(builder_provider="test", eval_provider="test", pipeline="test")
    state = LoopState(session_id=session.id, goal="goal", plan="plan")

    final = run_loop(
        FailingBuilder(),
        evaluator,
        state,
        config=LoopConfig(max_iterations=3, stop_on_error=False),
        observer=Observer(session=session),
        session=session,
    )

    assert session.load_meta().status == "failed"
