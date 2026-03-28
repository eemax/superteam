from __future__ import annotations

from superteam.core.contracts import LoopState, Verdict
from superteam.core.session import Session


def test_session_lifecycle_writes_expected_files():
    session = Session.create(builder_provider="builder", eval_provider="evaluator", pipeline="pipeline")

    meta = session.load_meta()
    assert meta.status == "running"
    assert session.meta_path.exists()

    state = LoopState(session_id=session.id, goal="goal", plan="plan", iteration=1, output="done")
    verdict = Verdict(status="pass", feedback="ok", score=1.0)
    session.checkpoint(state, verdict)
    session.finish("done", score=1.0)

    assert session.state_path.exists()
    assert (session.iterations_dir / "001.json").exists()
    assert (session.iterations_dir / "001.verdict.json").exists()
    assert session.load_meta().iterations == 1
    assert session.load_meta().status == "done"


def test_open_and_list_do_not_mutate_session_files():
    session = Session.create(builder_provider="builder", eval_provider="evaluator", pipeline="pipeline")
    before = session.meta_path.read_text(encoding="utf-8")

    opened = Session.open(session.id)
    listed = Session.list_all()
    after = session.meta_path.read_text(encoding="utf-8")

    assert opened.id == session.id
    assert any(item.id == session.id for item in listed)
    assert before == after
