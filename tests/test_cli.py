from __future__ import annotations

from pathlib import Path
import json
import time

from typer.testing import CliRunner

from superteam.cli.main import app
from superteam.core.session import Session


runner = CliRunner()


def test_cli_run_status_watch_and_result(tmp_path):
    pipeline_path = tmp_path / "pipeline.yaml"
    pipeline_path.write_text(
        """
name: test-loop
loop:
  max_iterations: 3
agents:
  builder:
    provider: fake_builder
    outputs:
      - "first draft"
      - "final draft"
  evaluator:
    provider: fake_evaluator
    responses:
      - status: fail
        feedback: fix it
        score: 0.1
      - status: pass
        feedback: looks good
        score: 0.95
input:
  plan: "follow the spec"
""".strip(),
        encoding="utf-8",
    )

    run_result = runner.invoke(app, ["run", str(pipeline_path), "--goal", "build it"])
    assert run_result.exit_code == 0, run_result.output

    session_id = next(line for line in run_result.output.splitlines() if line.startswith("st-"))
    status_result = runner.invoke(app, ["status", session_id])
    assert status_result.exit_code == 0
    payload = json.loads(status_result.output)
    assert payload["status"] == "done"
    assert payload["iteration"] == 2

    watch_result = runner.invoke(app, ["watch", session_id])
    assert watch_result.exit_code == 0
    assert "step=builder" in watch_result.output
    assert "status=pass" in watch_result.output

    result_text = runner.invoke(app, ["result", session_id])
    assert result_text.exit_code == 0
    assert result_text.output.strip() == "final draft"

    result_json = runner.invoke(app, ["result", session_id, "--format", "json"])
    assert result_json.exit_code == 0
    parsed = json.loads(result_json.output)
    assert parsed["meta"]["status"] == "done"
    assert parsed["state"]["output"] == "final draft"


def test_cli_detach_writes_pid_and_completes(tmp_path):
    pipeline_path = tmp_path / "detach.yaml"
    pipeline_path.write_text(
        """
name: detach-loop
loop:
  max_iterations: 1
agents:
  builder:
    provider: fake_builder
    outputs:
      - "background output"
  evaluator:
    provider: fake_evaluator
    responses:
      - status: pass
        feedback: ok
        score: 1.0
""".strip(),
        encoding="utf-8",
    )

    detach = runner.invoke(app, ["run", str(pipeline_path), "--goal", "ship it", "--detach"])
    assert detach.exit_code == 0, detach.output
    session_id = detach.output.strip()
    session = Session.open(session_id)
    assert session.load_run_pid() is not None

    deadline = time.time() + 10
    while time.time() < deadline:
        if session.load_meta().status in {"done", "failed"}:
            break
        time.sleep(0.2)

    assert session.load_meta().status == "done"
    result = runner.invoke(app, ["result", session_id])
    assert result.output.strip() == "background output"


def test_cli_sessions_list_returns_created_sessions(tmp_path):
    pipeline_path = tmp_path / "list-test.yaml"
    pipeline_path.write_text(
        """
name: list-loop
loop:
  max_iterations: 1
agents:
  builder:
    provider: fake_builder
    outputs:
      - "output"
  evaluator:
    provider: fake_evaluator
    responses:
      - status: pass
        feedback: ok
        score: 1.0
""".strip(),
        encoding="utf-8",
    )

    run_result = runner.invoke(app, ["run", str(pipeline_path), "--goal", "test"])
    assert run_result.exit_code == 0
    session_id = next(line for line in run_result.output.splitlines() if line.startswith("st-"))

    list_result = runner.invoke(app, ["sessions", "list"])
    assert list_result.exit_code == 0
    assert session_id in list_result.output

    list_json = runner.invoke(app, ["sessions", "list", "--format", "json"])
    assert list_json.exit_code == 0
    parsed = json.loads(list_json.output)
    assert any(s["session_id"] == session_id for s in parsed)

    filtered = runner.invoke(app, ["sessions", "list", "--status", "done"])
    assert filtered.exit_code == 0
    assert session_id in filtered.output

    empty = runner.invoke(app, ["sessions", "list", "--status", "running"])
    assert empty.exit_code == 0


def test_cli_status_text_format(tmp_path):
    pipeline_path = tmp_path / "status-text.yaml"
    pipeline_path.write_text(
        """
name: status-loop
loop:
  max_iterations: 1
agents:
  builder:
    provider: fake_builder
    outputs:
      - "output"
  evaluator:
    provider: fake_evaluator
    responses:
      - status: pass
        feedback: ok
        score: 1.0
""".strip(),
        encoding="utf-8",
    )

    run_result = runner.invoke(app, ["run", str(pipeline_path), "--goal", "test"])
    assert run_result.exit_code == 0
    session_id = next(line for line in run_result.output.splitlines() if line.startswith("st-"))

    text_result = runner.invoke(app, ["status", session_id, "--format", "text"])
    assert text_result.exit_code == 0
    assert f"session_id={session_id}" in text_result.output
    assert "status=done" in text_result.output


def test_cli_result_returns_full_spilled_artifact(tmp_path):
    long_output = "x" * 9001
    pipeline_path = tmp_path / "spill.yaml"
    pipeline_path.write_text(
        f"""
name: spill-loop
loop:
  max_iterations: 1
agents:
  builder:
    provider: fake_builder
    outputs:
      - "{long_output}"
  evaluator:
    provider: fake_evaluator
    responses:
      - status: pass
        feedback: ok
        score: 1.0
""".strip(),
        encoding="utf-8",
    )

    run_result = runner.invoke(app, ["run", str(pipeline_path), "--goal", "spill it"])
    assert run_result.exit_code == 0, run_result.output
    session_id = next(line for line in run_result.output.splitlines() if line.startswith("st-"))

    result = runner.invoke(app, ["result", session_id])
    assert result.exit_code == 0
    assert result.output.strip() == long_output


def test_cli_run_respects_global_config(tmp_path, monkeypatch):
    """CLI run should pick up global config via prepare_run().

    Precedence: pipeline YAML > global config. The pipeline does not set
    outputs, so the global config value should fill in.
    """
    monkeypatch.setenv("SUPERTEAM_HOME", str(tmp_path))

    config_path = tmp_path / "config.toml"
    config_path.write_text(
        '[providers.fake_builder]\noutputs = ["global-output"]\n',
        encoding="utf-8",
    )

    pipeline_path = tmp_path / "pipe.yaml"
    pipeline_path.write_text(
        """
name: global-test
loop:
  max_iterations: 1
agents:
  builder:
    provider: fake_builder
  evaluator:
    provider: fake_evaluator
    responses:
      - status: pass
        feedback: ok
        score: 1.0
""".strip(),
        encoding="utf-8",
    )

    run_result = runner.invoke(app, ["run", str(pipeline_path), "--goal", "test global"])
    assert run_result.exit_code == 0, run_result.output
    session_id = next(line for line in run_result.output.splitlines() if line.startswith("st-"))

    result = runner.invoke(app, ["result", session_id])
    assert result.exit_code == 0
    # Global config fills in outputs not set by the pipeline
    assert result.output.strip() == "global-output"
