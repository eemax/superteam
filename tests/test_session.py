from __future__ import annotations

from superteam.core.contracts import InvocationRecord, LoopState, Verdict
from superteam.core.session import Session


def test_session_lifecycle_writes_expected_files():
    session = Session.create(builder_module="builder", auditor_module="auditor", pipeline="pipeline")

    meta = session.load_meta()
    assert meta.status == "running"
    assert session.meta_path.exists()

    state = LoopState(session_id=session.id, goal="goal", plan="plan", iteration=1, output="done")
    verdict = Verdict(
        status="pass",
        audit_verdict="PASS",
        feedback="# Agent Audit\n\n## 1. Context\nReviewed.\n\n## 2. Verdict\n**PASS**\n\n**Rationale:** Ready.\n\n**Confidence:** High\n\n## 3. Findings Summary\n- **P1 - Critical:** 0\n- **P2 - Major:** 0\n- **P3 - Minor:** 0\n\n## 4. Findings\nNo open findings.\n\n## 5. Recommendations\n### Before Ship\n- None.\n\n### Before Next Milestone\n- None.\n\n### Longer-Term Improvements\n- None.\n\n## 6. Audit Details\n- **Files reviewed:** []\n- **Tests run:** []\n- **Results:** 0 passed, 0 failed, 0 skipped\n- **Tools used:** [\"static review\"]\n- **Method:** static review\n- **Environment:** tests\n- **Reference:** fixture\n- **Audited by:** tests\n- **Timestamp:** 2026-03-31T00:00:00+07:00\n\n## 7. Scope Exclusions\n- None.",
        score=1.0,
        next_steps=[],
        metadata={},
    )
    session.checkpoint(state, verdict)
    session.record_invocation(
        InvocationRecord(
            index=0,
            iteration=1,
            module="codex",
            role="builder",
            attempt=1,
            started_at=1.0,
            ended_at=2.0,
            duration_seconds=1.0,
            cwd="/tmp/project",
            system="sys",
            prompt="prompt",
            output="output",
        )
    )
    session.finish("done", score=1.0)

    assert session.state_path.exists()
    assert (session.iterations_dir / "001.json").exists()
    assert (session.iterations_dir / "001.verdict.json").exists()
    assert (session.invocations_dir / "0001.json").exists()
    assert session.load_meta().iterations == 1
    assert session.load_meta().status == "done"


def test_open_and_list_do_not_mutate_session_files():
    session = Session.create(builder_module="builder", auditor_module="auditor", pipeline="pipeline")
    before = session.meta_path.read_text(encoding="utf-8")

    opened = Session.open(session.id)
    listed = Session.list_all()
    after = session.meta_path.read_text(encoding="utf-8")

    assert opened.id == session.id
    assert any(item.id == session.id for item in listed)
    assert before == after
