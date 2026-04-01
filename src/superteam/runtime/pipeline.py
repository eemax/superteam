from __future__ import annotations

from dataclasses import dataclass
from importlib.resources import files
from pathlib import Path
from typing import Any

from superteam.core.loop import LoopConfig
from superteam.modules.claude_code import ClaudeCodeConfig, ClaudeCodeModule
from superteam.modules.codex import CodexConfig, CodexModule
from superteam.modules.testing import (
    StaticAuditorModule,
    StaticAuditorModuleConfig,
    StaticBuilderModule,
    StaticBuilderModuleConfig,
)
from superteam.runtime.config import deep_merge, filter_dataclass_kwargs, load_global_config


BUILTIN_PIPELINES = {
    "code-review-loop": "code-review-loop.yaml",
    "qa-loop": "qa-loop.yaml",
}


@dataclass
class AgentSpec:
    module: str
    system: str
    config: dict[str, Any]


@dataclass
class PipelineSpec:
    name: str
    version: str | None
    description: str | None
    loop: LoopConfig
    builder: AgentSpec
    auditor: AgentSpec
    input_defaults: dict[str, Any]
    source: str
    raw: dict[str, Any]


def load_pipeline(path_or_name: str) -> PipelineSpec:
    raw = _load_yaml(path_or_name)
    agents = raw.get("agents", {})
    if "builder" not in agents or "auditor" not in agents:
        raise ValueError("Pipeline must define agents.builder and agents.auditor")

    return PipelineSpec(
        name=raw.get("name") or Path(path_or_name).stem,
        version=raw.get("version"),
        description=raw.get("description"),
        loop=LoopConfig(**raw.get("loop", {})),
        builder=_parse_agent(agents["builder"]),
        auditor=_parse_agent(agents["auditor"]),
        input_defaults=raw.get("input", {}),
        source=path_or_name,
        raw=raw,
    )


def module_registry() -> dict[str, tuple[type, type]]:
    return {
        "claude_code": (ClaudeCodeConfig, ClaudeCodeModule),
        "codex": (CodexConfig, CodexModule),
        "fake_builder": (StaticBuilderModuleConfig, StaticBuilderModule),
        "fake_auditor": (StaticAuditorModuleConfig, StaticAuditorModule),
    }


def instantiate_module(agent: AgentSpec):
    registry = module_registry()
    if agent.module not in registry:
        supported = ", ".join(sorted(registry))
        raise ValueError(f"Unsupported module '{agent.module}'. Available: {supported}")

    config_type, module_type = registry[agent.module]
    config_kwargs = filter_dataclass_kwargs(config_type, agent.config)
    config = config_type(**config_kwargs)
    return module_type(config)


@dataclass
class PreparedRun:
    pipeline_name: str
    loop_config: LoopConfig
    builder: Any
    auditor: Any
    builder_system: str
    auditor_system: str
    goal: str
    plan: str
    cwd: str | None = None
    builder_module_name: str = ""
    auditor_module_name: str = ""


def prepare_run(
    path_or_name: str,
    goal: str | None = None,
    plan: str | None = None,
    cwd: str | None = None,
    config_path: Path | None = None,
) -> PreparedRun:
    spec = load_pipeline(path_or_name)
    global_cfg = load_global_config(config_path)

    def _merge_agent(agent: AgentSpec) -> AgentSpec:
        module_globals = global_cfg.get("modules", {}).get(agent.module, {})
        merged = deep_merge(module_globals, agent.config)
        return AgentSpec(module=agent.module, system=agent.system, config=merged)

    builder_agent = _merge_agent(spec.builder)
    auditor_agent = _merge_agent(spec.auditor)

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
        builder=_instantiate_role_module(builder_agent, "builder"),
        auditor=_instantiate_role_module(auditor_agent, "auditor"),
        builder_system=builder_agent.system or "You are an expert builder. Execute the plan precisely.",
        auditor_system=auditor_agent.system or "You are a rigorous QA auditor. Return only the canonical Markdown audit report.",
        goal=resolved_goal,
        plan=resolved_plan,
        cwd=cwd,
        builder_module_name=spec.builder.module,
        auditor_module_name=spec.auditor.module,
    )


def _parse_agent(raw: dict[str, Any]) -> AgentSpec:
    if "module" not in raw:
        raise ValueError("Agent must declare a module")
    raw = dict(raw)
    module = raw.pop("module")
    system = raw.pop("system", "")
    return AgentSpec(module=module, system=system, config=raw)


def _instantiate_role_module(agent: AgentSpec, role: str):
    module = instantiate_module(agent)
    capabilities = getattr(module, "capabilities", lambda: set())()
    if role not in set(capabilities):
        raise ValueError(f"Module '{agent.module}' does not support the {role} role")
    return module


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
