from __future__ import annotations

from dataclasses import dataclass, fields
from importlib.resources import files
from pathlib import Path
from typing import Any

from superteam.core.loop import LoopConfig
from superteam.providers.claude_api import ClaudeAPIConfig, ClaudeAPIProvider
from superteam.providers.claude_code import ClaudeCodeConfig, ClaudeCodeProvider
from superteam.providers.testing import StaticBuilderConfig, StaticBuilderProvider, StaticEvaluatorConfig, StaticEvaluatorProvider
from superteam.runtime.config import deep_merge, filter_dataclass_kwargs, load_global_config


BUILTIN_PIPELINES = {
    "code-review-loop": "code-review-loop.yaml",
    "qa-loop": "qa-loop.yaml",
}


@dataclass
class AgentSpec:
    provider: str
    system: str
    config: dict[str, Any]


@dataclass
class PipelineSpec:
    name: str
    version: str | None
    description: str | None
    loop: LoopConfig
    builder: AgentSpec
    evaluator: AgentSpec
    input_defaults: dict[str, Any]
    source: str
    raw: dict[str, Any]


def load_pipeline(path_or_name: str) -> PipelineSpec:
    raw = _load_yaml(path_or_name)
    agents = raw.get("agents", {})
    if "builder" not in agents or "evaluator" not in agents:
        raise ValueError("Pipeline must define agents.builder and agents.evaluator")

    return PipelineSpec(
        name=raw.get("name") or Path(path_or_name).stem,
        version=raw.get("version"),
        description=raw.get("description"),
        loop=LoopConfig(**raw.get("loop", {})),
        builder=_parse_agent(agents["builder"]),
        evaluator=_parse_agent(agents["evaluator"]),
        input_defaults=raw.get("input", {}),
        source=path_or_name,
        raw=raw,
    )


def _provider_registry() -> dict[str, tuple[type, type]]:
    registry: dict[str, tuple[type, type]] = {
        "claude_api": (ClaudeAPIConfig, ClaudeAPIProvider),
        "claude_code": (ClaudeCodeConfig, ClaudeCodeProvider),
        "fake_builder": (StaticBuilderConfig, StaticBuilderProvider),
        "fake_evaluator": (StaticEvaluatorConfig, StaticEvaluatorProvider),
    }
    try:
        from superteam.providers.openrouter import OpenRouterConfig, OpenRouterProvider
        registry["openrouter"] = (OpenRouterConfig, OpenRouterProvider)
    except ImportError:
        pass
    return registry


def instantiate_provider(agent: AgentSpec):
    registry = _provider_registry()
    if agent.provider not in registry:
        supported = ", ".join(sorted(registry))
        raise ValueError(f"Unsupported provider '{agent.provider}'. Available: {supported}")

    config_type, provider_type = registry[agent.provider]
    config_kwargs = filter_dataclass_kwargs(config_type, agent.config)
    config = config_type(**config_kwargs)
    return provider_type(config)


@dataclass
class PreparedRun:
    pipeline_name: str
    loop_config: LoopConfig
    builder: Any
    evaluator: Any
    builder_system: str
    evaluator_system: str
    goal: str
    plan: str
    builder_provider_name: str = ""
    evaluator_provider_name: str = ""


def prepare_run(
    path_or_name: str,
    goal: str | None = None,
    plan: str | None = None,
    config_path: Path | None = None,
) -> PreparedRun:
    spec = load_pipeline(path_or_name)
    global_cfg = load_global_config(config_path)

    def _merge_agent(agent: AgentSpec) -> AgentSpec:
        provider_globals = global_cfg.get("providers", {}).get(agent.provider, {})
        merged = deep_merge(provider_globals, agent.config)
        return AgentSpec(provider=agent.provider, system=agent.system, config=merged)

    builder_agent = _merge_agent(spec.builder)
    evaluator_agent = _merge_agent(spec.evaluator)

    loop_overrides = global_cfg.get("loop", {})
    if loop_overrides:
        loop_kwargs = filter_dataclass_kwargs(LoopConfig, deep_merge(spec.raw.get("loop", {}), loop_overrides))
        loop_config = LoopConfig(**loop_kwargs)
    else:
        loop_config = spec.loop

    resolved_goal = goal or spec.input_defaults.get("goal")
    if not resolved_goal:
        raise ValueError("A goal is required either via argument or pipeline input.goal")
    resolved_plan = plan or spec.input_defaults.get("plan") or resolved_goal

    return PreparedRun(
        pipeline_name=spec.name,
        loop_config=loop_config,
        builder=instantiate_provider(builder_agent),
        evaluator=instantiate_provider(evaluator_agent),
        builder_system=builder_agent.system or "You are an expert builder. Execute the plan precisely.",
        evaluator_system=evaluator_agent.system or "You are a rigorous QA evaluator. Return only the canonical Markdown audit report.",
        goal=resolved_goal,
        plan=resolved_plan,
        builder_provider_name=spec.builder.provider,
        evaluator_provider_name=spec.evaluator.provider,
    )


def _parse_agent(raw: dict[str, Any]) -> AgentSpec:
    if "provider" not in raw:
        raise ValueError("Agent must declare a provider")
    raw = dict(raw)
    provider = raw.pop("provider")
    system = raw.pop("system", "")
    return AgentSpec(provider=provider, system=system, config=raw)


def _load_yaml(path_or_name: str) -> dict[str, Any]:
    try:
        import yaml
    except ImportError as exc:
        raise RuntimeError("PyYAML is required for pipeline loading. Install with the 'cli' extra.") from exc

    candidate = Path(path_or_name).expanduser()
    if candidate.exists():
        return yaml.safe_load(candidate.read_text(encoding="utf-8")) or {}
    if not candidate.suffix and candidate.with_suffix(".yaml").exists():
        return yaml.safe_load(candidate.with_suffix(".yaml").read_text(encoding="utf-8")) or {}

    builtin_name = BUILTIN_PIPELINES.get(path_or_name)
    if builtin_name is None:
        raise FileNotFoundError(f"Could not find pipeline '{path_or_name}'")
    raw = files("superteam.pipelines").joinpath(builtin_name).read_text(encoding="utf-8")
    return yaml.safe_load(raw) or {}
