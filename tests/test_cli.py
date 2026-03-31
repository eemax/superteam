from __future__ import annotations

import json
import os
import time

from typer.testing import CliRunner

import superteam.runtime.pipeline as runtime_pipeline
from superteam.cli.main import app
from superteam.core.session import Session


runner = CliRunner()


def _yaml_response(
    status: str,
    audit_verdict: str,
    score: float,
    feedback: str,
    next_steps: list[str] | None = None,
) -> str:
    next_steps = next_steps or []
    if next_steps:
        next_steps_block = "        next_steps:\n" + "".join(f"          - {step}\n" for step in next_steps)
    else:
        next_steps_block = "        next_steps: []\n"
    return (
        f"      - status: {status}\n"
        f"        audit_verdict: {audit_verdict}\n"
        f"        score: {score}\n"
        f"{next_steps_block}"
        "        metadata: {}\n"
        f"        feedback: {feedback}\n"
    )


def test_cli_run_status_watch_and_result(tmp_path):
    pipeline_path = tmp_path / "pipeline.yaml"
    pipeline_path.write_text(
        (
            """
name: test-loop
loop:
  max_iterations: 3
agents:
  builder:
    module: fake_builder
    outputs:
      - "first draft"
      - "final draft"
  auditor:
    module: fake_auditor
    responses:
"""
            + _yaml_response("fail", "FAIL", 0.1, "fix it", ["Fix it"])
            + _yaml_response("pass", "PASS", 0.95, "looks good")
            + """
input:
  plan: "follow the spec"
"""
        ).strip(),
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
    assert payload["builder_module"] == "fake_builder"
    assert payload["auditor_module"] == "fake_auditor"

    watch_result = runner.invoke(app, ["watch", session_id])
    assert watch_result.exit_code == 0
    assert "step=builder" in watch_result.output
    assert "status=pass" in watch_result.output
    assert "audit_verdict=PASS" in watch_result.output

    result_text = runner.invoke(app, ["result", session_id])
    assert result_text.exit_code == 0
    assert result_text.output.strip() == "final draft"

    result_json = runner.invoke(app, ["result", session_id, "--format", "json"])
    assert result_json.exit_code == 0
    parsed = json.loads(result_json.output)
    assert parsed["meta"]["status"] == "done"
    assert parsed["state"]["output"] == "final draft"


def test_cli_detach_writes_pid_completes_and_preserves_cwd(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    pipeline_path = tmp_path / "detach.yaml"
    pipeline_path.write_text(
        (
            """
name: detach-loop
loop:
  max_iterations: 1
agents:
  builder:
    module: fake_builder
    outputs:
      - "background output"
  auditor:
    module: fake_auditor
    responses:
"""
            + _yaml_response("pass", "PASS", 1.0, "ok")
        ).strip(),
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
    assert session.list_invocations()[0].cwd == str(tmp_path)


def test_cli_sessions_list_returns_created_sessions(tmp_path):
    pipeline_path = tmp_path / "list-test.yaml"
    pipeline_path.write_text(
        (
            """
name: list-loop
loop:
  max_iterations: 1
agents:
  builder:
    module: fake_builder
    outputs:
      - "output"
  auditor:
    module: fake_auditor
    responses:
"""
            + _yaml_response("pass", "PASS", 1.0, "ok")
        ).strip(),
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
        (
            """
name: status-loop
loop:
  max_iterations: 1
agents:
  builder:
    module: fake_builder
    outputs:
      - "output"
  auditor:
    module: fake_auditor
    responses:
"""
            + _yaml_response("pass", "PASS", 1.0, "ok")
        ).strip(),
        encoding="utf-8",
    )

    run_result = runner.invoke(app, ["run", str(pipeline_path), "--goal", "test"])
    assert run_result.exit_code == 0
    session_id = next(line for line in run_result.output.splitlines() if line.startswith("st-"))

    text_result = runner.invoke(app, ["status", session_id, "--format", "text"])
    assert text_result.exit_code == 0
    assert f"session_id={session_id}" in text_result.output
    assert "status=done" in text_result.output
    assert "builder_module=fake_builder" in text_result.output


def test_cli_result_returns_full_spilled_artifact(tmp_path):
    long_output = "x" * 9001
    pipeline_path = tmp_path / "spill.yaml"
    pipeline_path.write_text(
        (
            f"""
name: spill-loop
loop:
  max_iterations: 1
agents:
  builder:
    module: fake_builder
    outputs:
      - "{long_output}"
  auditor:
    module: fake_auditor
    responses:
"""
            + _yaml_response("pass", "PASS", 1.0, "ok")
        ).strip(),
        encoding="utf-8",
    )

    run_result = runner.invoke(app, ["run", str(pipeline_path), "--goal", "spill it"])
    assert run_result.exit_code == 0, run_result.output
    session_id = next(line for line in run_result.output.splitlines() if line.startswith("st-"))

    result = runner.invoke(app, ["result", session_id])
    assert result.exit_code == 0
    assert result.output.strip() == long_output


def test_cli_run_respects_global_config(tmp_path, monkeypatch):
    monkeypatch.setenv("SUPERTEAM_HOME", str(tmp_path))

    config_path = tmp_path / "config.toml"
    config_path.write_text(
        '[modules.fake_builder]\noutputs = ["global-output"]\n',
        encoding="utf-8",
    )

    pipeline_path = tmp_path / "pipe.yaml"
    pipeline_path.write_text(
        (
            """
name: global-test
loop:
  max_iterations: 1
agents:
  builder:
    module: fake_builder
  auditor:
    module: fake_auditor
    responses:
"""
            + _yaml_response("pass", "PASS", 1.0, "ok")
        ).strip(),
        encoding="utf-8",
    )

    run_result = runner.invoke(app, ["run", str(pipeline_path), "--goal", "test global"])
    assert run_result.exit_code == 0, run_result.output
    session_id = next(line for line in run_result.output.splitlines() if line.startswith("st-"))

    result = runner.invoke(app, ["result", session_id])
    assert result.exit_code == 0
    assert result.output.strip() == "global-output"


def test_cli_audit_outputs_markdown():
    audit_result = runner.invoke(
        app,
        ["audit", "--goal", "Confirm this is ship-ready", "--module", "fake_auditor"],
        input="builder output",
    )

    assert audit_result.exit_code == 0, audit_result.output
    assert audit_result.output.startswith("---\nstatus: pass\n")
    assert "audit_verdict: PASS" in audit_result.output
    assert "# Agent Audit" in audit_result.output


def test_cli_audit_requires_module():
    audit_result = runner.invoke(app, ["audit", "--goal", "Confirm this is ship-ready"], input="builder output")

    assert audit_result.exit_code != 0
    assert "--module" in audit_result.output


def test_cli_audit_fails_on_invalid_output(monkeypatch):
    class BrokenModule:
        def run(self, role: str, system: str, prompt: str, state=None, cwd=None) -> str:
            return "not markdown"

        def capabilities(self):
            return {"auditor"}

    monkeypatch.setattr(runtime_pipeline, "instantiate_module", lambda agent: BrokenModule())

    audit_result = runner.invoke(
        app,
        ["audit", "--goal", "Confirm this is ship-ready", "--module", "fake_auditor"],
        input="builder output",
    )

    assert audit_result.exit_code == 1
    assert "Could not parse auditor audit report:" in audit_result.output
    assert "Verdict must start with YAML frontmatter" in audit_result.output


def test_cli_audit_rejects_unknown_module():
    audit_result = runner.invoke(
        app,
        ["audit", "--goal", "Confirm this is ship-ready", "--module", "openrouter"],
        input="builder output",
    )

    assert audit_result.exit_code == 1
    assert "Unknown module: openrouter" in audit_result.output
