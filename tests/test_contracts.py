from __future__ import annotations

from superteam.core.contracts import Event, IterationRecord, LoopState, Verdict


def test_loop_state_round_trip_preserves_history():
    verdict = Verdict(status="pass", feedback="looks good", score=0.91, metadata={"source": "test"})
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
        context={"attempts": 1},
        history=[record],
    )

    loaded = LoopState.from_json(state.to_json())

    assert loaded == state


def test_event_jsonl_round_trip():
    event = Event(ts=123.45, event="verdict", payload={"iteration": 2, "status": "pass"})

    loaded = Event.from_jsonl(event.to_jsonl())

    assert loaded == event
