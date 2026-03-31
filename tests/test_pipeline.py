from __future__ import annotations

import pytest

from superteam.runtime.pipeline import (
    AgentSpec,
    PreparedRun,
    _module_registry,
    instantiate_module,
    load_pipeline,
    prepare_run,
)


def test_load_builtin_pipeline_code_review_loop():
    spec = load_pipeline("code-review-loop")
    assert spec.name == "code-review-loop"
    assert spec.builder.module == "claude_code"
    assert spec.auditor.module == "codex"


def test_load_builtin_pipeline_qa_loop():
    spec = load_pipeline("qa-loop")
    assert spec.name == "qa-loop"
    assert spec.builder.module == "codex"
    assert spec.auditor.module == "claude_code"


def test_removed_builtin_pipeline_is_not_loadable():
    with pytest.raises(FileNotFoundError):
        load_pipeline("write-and-critique")


def test_load_pipeline_by_file_path(tmp_path):
    pipeline = tmp_path / "custom.yaml"
    pipeline.write_text(
        "name: custom\nagents:\n  builder:\n    module: fake_builder\n  auditor:\n    module: fake_auditor\n"
    )
    spec = load_pipeline(str(pipeline))
    assert spec.name == "custom"


def test_load_pipeline_tries_yaml_suffix(tmp_path):
    pipeline = tmp_path / "my-pipeline.yaml"
    pipeline.write_text(
        "name: my-pipeline\nagents:\n  builder:\n    module: fake_builder\n  auditor:\n    module: fake_auditor\n"
    )
    spec = load_pipeline(str(tmp_path / "my-pipeline"))
    assert spec.name == "my-pipeline"


def test_load_pipeline_not_found():
    with pytest.raises(FileNotFoundError):
        load_pipeline("nonexistent-pipeline")


def test_instantiate_module_invalid_name():
    agent = AgentSpec(module="doesnt_exist", system="", config={})
    with pytest.raises(ValueError, match="Unsupported module"):
        instantiate_module(agent)


def test_instantiate_fake_builder_module():
    agent = AgentSpec(module="fake_builder", system="sys", config={"outputs": ["hello"]})
    module = instantiate_module(agent)
    assert module.run("builder", "sys", "prompt") == "hello"


def test_module_registry_includes_codex_and_claude():
    registry = _module_registry()
    assert "codex" in registry
    assert "claude_code" in registry


def test_prepare_run_with_global_config(tmp_path):
    pipeline = tmp_path / "prep.yaml"
    pipeline.write_text(
        """
name: prep-test
agents:
  builder:
    module: fake_builder
    outputs:
      - "hi"
  auditor:
    module: fake_auditor
    responses:
      - status: pass
        audit_verdict: PASS
        score: 1.0
        next_steps: []
        metadata: {}
        feedback: ok
input:
  goal: default-goal
""".strip()
    )
    config = tmp_path / "config.toml"
    config.write_text("")

    run = prepare_run(str(pipeline), cwd=str(tmp_path), config_path=config)
    assert isinstance(run, PreparedRun)
    assert run.goal == "default-goal"
    assert run.plan == "default-goal"
    assert run.cwd == str(tmp_path)


def test_prepare_run_cli_goal_overrides_pipeline(tmp_path):
    pipeline = tmp_path / "override.yaml"
    pipeline.write_text(
        """
name: override-test
agents:
  builder:
    module: fake_builder
  auditor:
    module: fake_auditor
input:
  goal: pipeline-goal
""".strip()
    )

    run = prepare_run(str(pipeline), goal="cli-goal")
    assert run.goal == "cli-goal"


def test_prepare_run_requires_goal(tmp_path):
    pipeline = tmp_path / "nogoal.yaml"
    pipeline.write_text(
        "name: no-goal\nagents:\n  builder:\n    module: fake_builder\n  auditor:\n    module: fake_auditor\n"
    )
    with pytest.raises(ValueError, match="goal is required"):
        prepare_run(str(pipeline))


def test_prepare_run_rejects_role_mismatch(tmp_path):
    pipeline = tmp_path / "mismatch.yaml"
    pipeline.write_text(
        """
name: mismatch
agents:
  builder:
    module: fake_builder
  auditor:
    module: fake_builder
input:
  goal: test
""".strip()
    )

    with pytest.raises(ValueError, match="does not support the auditor role"):
        prepare_run(str(pipeline))
