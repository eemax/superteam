from __future__ import annotations

from pathlib import Path

import pytest

from superteam.runtime.pipeline import (
    AgentSpec,
    PreparedRun,
    instantiate_provider,
    load_pipeline,
    prepare_run,
    _provider_registry,
)


def test_load_builtin_pipeline_code_review_loop():
    spec = load_pipeline("code-review-loop")
    assert spec.name == "code-review-loop"
    assert spec.builder.provider == "claude_code"
    assert spec.evaluator.provider == "claude_api"


def test_load_builtin_pipeline_qa_loop():
    spec = load_pipeline("qa-loop")
    assert spec.name == "qa-loop"
    assert spec.builder.provider == "claude_code"
    assert spec.evaluator.provider == "openrouter"


def test_removed_builtin_pipeline_is_not_loadable():
    with pytest.raises(FileNotFoundError):
        load_pipeline("write-and-critique")


def test_load_pipeline_by_file_path(tmp_path):
    pipeline = tmp_path / "custom.yaml"
    pipeline.write_text(
        "name: custom\nagents:\n  builder:\n    provider: fake_builder\n  evaluator:\n    provider: fake_evaluator\n"
    )
    spec = load_pipeline(str(pipeline))
    assert spec.name == "custom"


def test_load_pipeline_tries_yaml_suffix(tmp_path):
    pipeline = tmp_path / "my-pipeline.yaml"
    pipeline.write_text(
        "name: my-pipeline\nagents:\n  builder:\n    provider: fake_builder\n  evaluator:\n    provider: fake_evaluator\n"
    )
    spec = load_pipeline(str(tmp_path / "my-pipeline"))
    assert spec.name == "my-pipeline"


def test_load_pipeline_not_found():
    with pytest.raises(FileNotFoundError):
        load_pipeline("nonexistent-pipeline")


def test_instantiate_provider_invalid_name():
    agent = AgentSpec(provider="doesnt_exist", system="", config={})
    with pytest.raises(ValueError, match="Unsupported provider"):
        instantiate_provider(agent)


def test_instantiate_fake_builder():
    agent = AgentSpec(provider="fake_builder", system="sys", config={"outputs": ["hello"]})
    provider = instantiate_provider(agent)
    assert provider.complete("sys", "prompt") == "hello"


def test_provider_registry_includes_openrouter():
    registry = _provider_registry()
    assert "openrouter" in registry


def test_prepare_run_with_global_config(tmp_path):
    pipeline = tmp_path / "prep.yaml"
    pipeline.write_text(
        """
name: prep-test
agents:
  builder:
    provider: fake_builder
    outputs:
      - "hi"
  evaluator:
    provider: fake_evaluator
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

    run = prepare_run(str(pipeline), config_path=config)
    assert isinstance(run, PreparedRun)
    assert run.goal == "default-goal"
    assert run.plan == "default-goal"


def test_prepare_run_cli_goal_overrides_pipeline(tmp_path):
    pipeline = tmp_path / "override.yaml"
    pipeline.write_text(
        """
name: override-test
agents:
  builder:
    provider: fake_builder
  evaluator:
    provider: fake_evaluator
input:
  goal: pipeline-goal
""".strip()
    )

    run = prepare_run(str(pipeline), goal="cli-goal")
    assert run.goal == "cli-goal"


def test_prepare_run_requires_goal(tmp_path):
    pipeline = tmp_path / "nogoal.yaml"
    pipeline.write_text(
        "name: no-goal\nagents:\n  builder:\n    provider: fake_builder\n  evaluator:\n    provider: fake_evaluator\n"
    )
    with pytest.raises(ValueError, match="goal is required"):
        prepare_run(str(pipeline))
