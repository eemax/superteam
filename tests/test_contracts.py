from __future__ import annotations

from superteam.core.contracts import Event, IterationRecord, LoopState, Verdict


def test_loop_state_round_trip_preserves_history():
    verdict = Verdict(
        status="pass",
        audit_verdict="PASS",
        feedback="# Agent Audit\n\n## 1. Context\nReviewed.\n\n## 2. Verdict\n**PASS**\n\n**Rationale:** Looks good.\n\n**Confidence:** High\n\n## 3. Findings Summary\n- **P1 - Critical:** 0\n- **P2 - Major:** 0\n- **P3 - Minor:** 0\n\n## 4. Findings\nNo open findings.\n\n## 5. Recommendations\n### Before Ship\n- None.\n\n### Before Next Milestone\n- None.\n\n### Longer-Term Improvements\n- None.\n\n## 6. Audit Details\n- **Files reviewed:** []\n- **Tests run:** []\n- **Results:** 0 passed, 0 failed, 0 skipped\n- **Tools used:** [\"static review\"]\n- **Method:** static review\n- **Environment:** tests\n- **Reference:** fixture\n- **Audited by:** tests\n- **Timestamp:** 2026-03-31T00:00:00+07:00\n\n## 7. Scope Exclusions\n- None.",
        score=0.91,
        next_steps=[],
        metadata={"source": "test"},
    )
    record = IterationRecord(
        iteration=1,
        ts_start=1.0,
        ts_end=2.0,
        output_preview="preview",
        output_ref="/tmp/artifact",
        verdict=verdict,
        tokens={"builder": {"input": 10, "output": 20, "total": 30}},
    )
    state = LoopState(
        session_id="st-test1234",
        goal="Build a thing",
        plan="1. Build it",
        iteration=1,
        output="final output",
        output_ref="/tmp/artifact",
        output_preview="preview",
        feedback="ship it",
        next_steps=["Run regression tests"],
        context={"attempts": 1},
        history=[record],
    )

    loaded = LoopState.from_json(state.to_json())

    assert loaded == state


def test_event_jsonl_round_trip():
    event = Event(ts=123.45, event="verdict", payload={"iteration": 2, "status": "pass"})

    loaded = Event.from_jsonl(event.to_jsonl())

    assert loaded == event
