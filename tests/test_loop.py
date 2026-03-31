from __future__ import annotations

from pathlib import Path

import pytest

from superteam.core.contracts import OUTPUT_INLINE_LIMIT, LoopState, Verdict
from superteam.core.loop import (
    LoopConfig,
    SessionArtifactStore,
    audit_report_format_instructions,
    build_auditor_prompt,
    build_builder_prompt,
    parse_verdict,
    run_loop,
    step_once,
)
from superteam.core.observe import Observer
from superteam.core.session import Session


STATUS_TO_AUDIT_VERDICT = {
    "pass": "PASS",
    "retry": "PASS WITH CONDITIONS",
    "fail": "FAIL",
}


def make_audit_body(summary: str, audit_verdict: str, next_steps: list[str]) -> str:
    before_ship = "\n".join(f"- {step}" for step in next_steps) if next_steps else "- None."
    return (
        "# Agent Audit\n\n"
        "## 1. Context\n"
        f"{summary}\n\n"
        "## 2. Verdict\n"
        f"**{audit_verdict}**\n\n"
        f"**Rationale:** {summary}\n\n"
        "**Confidence:** High\n\n"
        "## 3. Findings Summary\n"
        "- **P1 - Critical:** 0\n"
        "- **P2 - Major:** 0\n"
        "- **P3 - Minor:** 0\n\n"
        "## 4. Findings\n"
        "No additional findings.\n\n"
        "## 5. Recommendations\n"
        "### Before Ship\n"
        f"{before_ship}\n\n"
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
        "- **Environment:** tests\n"
        "- **Reference:** fixture\n"
        "- **Audited by:** tests\n"
        "- **Timestamp:** 2026-03-31T00:00:00+07:00\n\n"
        "## 7. Scope Exclusions\n"
        "- None."
    )


def make_verdict_markdown(
    status: str,
    score: float,
    summary: str,
    next_steps: list[str] | None = None,
    audit_verdict: str | None = None,
    body: str | None = None,
) -> str:
    next_steps = next_steps or []
    audit_verdict = audit_verdict or STATUS_TO_AUDIT_VERDICT[status]
    feedback = body or make_audit_body(summary, audit_verdict, next_steps)
    return Verdict(
        status=status,
        audit_verdict=audit_verdict,
        feedback=feedback,
        score=score,
        next_steps=next_steps,
        metadata={},
    ).to_markdown()


class SequenceBuilder:
    def __init__(self, outputs: list[str]):
        self.outputs = outputs
        self.calls = 0

    def run(self, role: str, system: str, prompt: str, state: LoopState | None = None, cwd: str | None = None) -> str:
        index = min(self.calls, len(self.outputs) - 1)
        self.calls += 1
        return self.outputs[index]

    def health(self) -> bool:
        return True


class SequenceAuditor:
    def __init__(self, responses: list[str]):
        self.responses = responses
        self.prompts: list[str] = []
        self.calls = 0

    def run(self, role: str, system: str, prompt: str, state: LoopState | None = None, cwd: str | None = None) -> str:
        index = min(self.calls, len(self.responses) - 1)
        response = self.responses[index]
        self.prompts.append(prompt)
        self.calls += 1
        return response

    def health(self) -> bool:
        return True


class FlakyBuilder:
    def __init__(self, failures: int, output: str):
        self.failures = failures
        self.output = output
        self.calls = 0

    def run(self, role: str, system: str, prompt: str, state: LoopState | None = None, cwd: str | None = None) -> str:
        self.calls += 1
        if self.calls <= self.failures:
            raise TimeoutError("temporary timeout")
        return self.output

    def health(self) -> bool:
        return True


def test_step_once_spills_large_output_and_auditor_reads_full_artifact():
    session = Session.create(builder_module="fake_builder", auditor_module="fake_auditor", pipeline="test")
    builder_output = "A" * (OUTPUT_INLINE_LIMIT + 250)
    builder = SequenceBuilder([builder_output])
    auditor = SequenceAuditor([make_verdict_markdown("pass", 1.0, "ok")])
    state = LoopState(session_id=session.id, goal="Review this", plan="Do it")

    next_state, verdict = step_once(
        builder,
        auditor,
        state,
        artifact_store=SessionArtifactStore(session),
    )

    assert verdict.status == "pass"
    assert next_state.output_ref is not None
    assert Path(next_state.output_ref).read_text(encoding="utf-8") == builder_output
    assert builder_output in auditor.prompts[0]
    assert next_state.output.startswith("[artifact spilled to")


def test_parse_verdict_repairs_invalid_markdown_once():
    class RepairAuditor:
        def __init__(self):
            self.calls = 0

        def run(self, role: str, system: str, prompt: str, state: LoopState | None = None, cwd: str | None = None) -> str:
            self.calls += 1
            return make_verdict_markdown("retry", 0.2, "fix markdown", ["Fix markdown format"])

    auditor = RepairAuditor()

    verdict = parse_verdict(
        "not markdown at all",
        config=LoopConfig(parse_repair_prompt=True),
        auditor=auditor,
        system="Return only the canonical Markdown audit report.",
    )

    assert verdict.status == "retry"
    assert verdict.audit_verdict == "PASS WITH CONDITIONS"
    assert verdict.next_steps == ["Fix markdown format"]
    assert auditor.calls == 1


def test_parse_verdict_rejects_json():
    with pytest.raises(ValueError):
        parse_verdict('{"status": "pass", "score": 1.0}')


def test_parse_verdict_rejects_mismatched_status_and_audit_verdict():
    raw = make_verdict_markdown("pass", 1.0, "looks good", audit_verdict="FAIL")

    with pytest.raises(ValueError, match="requires audit_verdict"):
        parse_verdict(raw, config=LoopConfig(parse_repair_prompt=False))


def test_parse_verdict_rejects_missing_required_sections():
    raw = """---
status: pass
audit_verdict: PASS
score: 1.0
next_steps: []
metadata: {}
---

# Agent Audit

## 1. Context
Reviewed.
"""

    with pytest.raises(ValueError, match="required sections"):
        parse_verdict(raw, config=LoopConfig(parse_repair_prompt=False))


def test_run_loop_retries_transient_errors_and_succeeds():
    builder = FlakyBuilder(failures=2, output="stable output")
    auditor = SequenceAuditor([make_verdict_markdown("pass", 0.99, "great")])
    state = LoopState(session_id="st-retry", goal="goal", plan="plan")

    final = run_loop(
        builder,
        auditor,
        state,
        config=LoopConfig(max_iterations=1, transient_retries=2),
        observer=Observer(),
    )

    assert final.iteration == 1
    assert builder.calls == 3
    assert final.history[-1].verdict.status == "pass"


def test_run_loop_does_not_finish_on_high_score_without_pass():
    builder = SequenceBuilder(["draft", "draft", "draft"])
    auditor = SequenceAuditor([make_verdict_markdown("retry", 0.95, "almost", ["Address remaining issues"])])
    session = Session.create(builder_module="fake_builder", auditor_module="fake_auditor", pipeline="score")
    state = LoopState(session_id=session.id, goal="goal", plan="plan")

    final = run_loop(
        builder,
        auditor,
        state,
        config=LoopConfig(max_iterations=3, min_score=0.9),
        observer=Observer(session=session),
        session=session,
        builder_module_name="fake_builder",
        auditor_module_name="fake_auditor",
    )

    assert final.iteration == 3
    assert session.load_meta().status == "failed"


def test_run_loop_requires_min_score_before_pass_completes():
    builder = SequenceBuilder(["draft one", "draft two"])
    auditor = SequenceAuditor(
        [
            make_verdict_markdown("pass", 0.7, "not enough yet"),
            make_verdict_markdown("pass", 0.95, "ready now"),
        ]
    )
    session = Session.create(builder_module="fake_builder", auditor_module="fake_auditor", pipeline="score")
    state = LoopState(session_id=session.id, goal="goal", plan="plan")

    final = run_loop(
        builder,
        auditor,
        state,
        config=LoopConfig(max_iterations=3, min_score=0.9),
        observer=Observer(session=session),
        session=session,
        builder_module_name="fake_builder",
        auditor_module_name="fake_auditor",
    )

    assert final.iteration == 2
    assert session.load_meta().status == "done"


def test_run_loop_marks_session_failed_on_max_iterations():
    builder = SequenceBuilder(["draft one", "draft two"])
    auditor = SequenceAuditor([make_verdict_markdown("fail", 0.1, "still wrong", ["Fix the blocking issue"])])
    session = Session.create(builder_module="fake_builder", auditor_module="fake_auditor", pipeline="max")
    state = LoopState(session_id=session.id, goal="goal", plan="plan")

    final = run_loop(
        builder,
        auditor,
        state,
        config=LoopConfig(max_iterations=2, on_max_iterations="fail"),
        observer=Observer(session=session),
        session=session,
        builder_module_name="fake_builder",
        auditor_module_name="fake_auditor",
    )

    assert final.iteration == 2
    assert session.load_meta().status == "failed"


def test_builder_prompt_loads_full_artifact_and_next_steps_when_spilled():
    large_output = "B" * 10_000
    session = Session.create(builder_module="test", auditor_module="test", pipeline="test")
    artifact_store = SessionArtifactStore(session)

    inline, ref, preview = artifact_store.spill(large_output, 1)
    state = LoopState(
        session_id=session.id,
        goal="goal",
        plan="plan",
        iteration=1,
        output=inline,
        output_ref=ref,
        feedback=make_audit_body("reviewed", "PASS WITH CONDITIONS", ["Add tests"]),
        next_steps=["Add tests"],
    )

    prompt = build_builder_prompt(state, artifact_store)
    assert large_output in prompt
    assert "## Previous audit report" in prompt
    assert "## Required next steps" in prompt
    assert "- Add tests" in prompt
    assert "[artifact spilled" not in prompt.split("## Previous output")[1]


def test_both_prompts_see_same_full_artifact():
    large_output = "C" * 10_000
    session = Session.create(builder_module="test", auditor_module="test", pipeline="test")
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
    auditor_prompt = build_auditor_prompt(state, artifact_store)
    assert large_output in builder_prompt
    assert large_output in auditor_prompt
    assert "canonical Markdown audit report" in auditor_prompt


def test_parse_verdict_repair_prompt_includes_original_response():
    class CapturingAuditor:
        def __init__(self):
            self.last_prompt = ""

        def run(self, role: str, system: str, prompt: str, state: LoopState | None = None, cwd: str | None = None) -> str:
            self.last_prompt = prompt
            return make_verdict_markdown("pass", 0.8, "fixed")

    auditor = CapturingAuditor()
    raw = "This is not valid markdown audit output"
    verdict = parse_verdict(
        raw,
        config=LoopConfig(parse_repair_prompt=True),
        auditor=auditor,
        system="Return only the canonical Markdown audit report.",
    )
    assert raw in auditor.last_prompt
    assert "canonical Markdown audit format" in auditor.last_prompt
    assert verdict.status == "pass"


def test_run_loop_stop_on_error_false_finishes_session_and_records_invocation():
    class FailingBuilder:
        def run(self, role: str, system: str, prompt: str, state: LoopState | None = None, cwd: str | None = None) -> str:
            raise RuntimeError("boom")

        def health(self) -> bool:
            return True

    auditor = SequenceAuditor([make_verdict_markdown("pass", 1.0, "ok")])
    session = Session.create(builder_module="test", auditor_module="test", pipeline="test")
    state = LoopState(session_id=session.id, goal="goal", plan="plan")

    run_loop(
        FailingBuilder(),
        auditor,
        state,
        config=LoopConfig(max_iterations=3, stop_on_error=False),
        observer=Observer(session=session),
        session=session,
        builder_module_name="test",
        auditor_module_name="test",
    )

    invocations = session.list_invocations()
    assert session.load_meta().status == "failed"
    assert len(invocations) == 1
    assert invocations[0].error == "boom"


def test_parse_verdict_accepts_integer_score():
    md = make_verdict_markdown("pass", 1, "all good")
    verdict = parse_verdict(md)
    assert verdict.score == 1.0
    assert verdict.status == "pass"


def test_parse_verdict_strips_code_fences():
    inner = make_verdict_markdown("pass", 0.95, "looks good")
    fenced = f"```markdown\n{inner}\n```"
    verdict = parse_verdict(fenced)
    assert verdict.status == "pass"
    assert verdict.score == 0.95


def test_run_loop_records_invocations_for_builder_auditor_and_repair():
    builder = SequenceBuilder(["draft"])
    auditor = SequenceAuditor(["not markdown", make_verdict_markdown("pass", 1.0, "fixed")])
    session = Session.create(builder_module="fake_builder", auditor_module="fake_auditor", pipeline="records")
    state = LoopState(session_id=session.id, goal="goal", plan="plan")

    final = run_loop(
        builder,
        auditor,
        state,
        config=LoopConfig(max_iterations=1, parse_repair_prompt=True),
        observer=Observer(session=session),
        session=session,
        builder_module_name="fake_builder",
        auditor_module_name="fake_auditor",
        cwd="/tmp/project",
    )

    invocations = session.list_invocations()
    assert final.history[-1].verdict.status == "pass"
    assert [record.role for record in invocations] == ["builder", "auditor", "auditor"]
    assert all(record.cwd == "/tmp/project" for record in invocations)


def test_run_loop_spills_large_invocation_payloads():
    large_output = "X" * 9001
    builder = SequenceBuilder([large_output])
    auditor = SequenceAuditor([make_verdict_markdown("pass", 1.0, "ok")])
    session = Session.create(builder_module="fake_builder", auditor_module="fake_auditor", pipeline="spill")
    state = LoopState(session_id=session.id, goal="goal", plan="plan")

    run_loop(
        builder,
        auditor,
        state,
        config=LoopConfig(max_iterations=1),
        observer=Observer(session=session),
        session=session,
        builder_module_name="fake_builder",
        auditor_module_name="fake_auditor",
    )

    builder_call, auditor_call = session.list_invocations()
    assert builder_call.output_ref is not None
    assert auditor_call.prompt_ref is not None
    assert Path(builder_call.output_ref).read_text(encoding="utf-8") == large_output


def test_audit_report_instructions_still_require_canonical_format():
    instructions = audit_report_format_instructions()
    assert "canonical Markdown audit report" in instructions
    assert "status: pass | fail | retry" in instructions
