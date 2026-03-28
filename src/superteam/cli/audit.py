from __future__ import annotations

import json
import sys
from dataclasses import asdict

import typer


def audit_command(
    goal: str = typer.Option(..., "--goal", help="Goal to evaluate against."),
    provider: str = typer.Option("claude_api", "--provider", help="Evaluator provider name."),
    model: str | None = typer.Option(None, "--model", help="Override provider model."),
) -> None:
    """Run evaluator on piped input. Usage: cat output.txt | superteam audit --goal '...'"""
    if sys.stdin.isatty():
        typer.echo("Pipe content to stdin. Example: cat output.txt | superteam audit --goal '...'", err=True)
        raise typer.Exit(1)

    content = sys.stdin.read()

    from superteam.runtime.pipeline import _provider_registry, AgentSpec, instantiate_provider
    from superteam.runtime.config import load_global_config, deep_merge

    registry = _provider_registry()
    if provider not in registry:
        supported = ", ".join(sorted(registry))
        typer.echo(f"Unknown provider: {provider}. Available: {supported}", err=True)
        raise typer.Exit(1)

    global_cfg = load_global_config()
    provider_globals = global_cfg.get("providers", {}).get(provider, {})
    config: dict = {}
    if model:
        config["model"] = model
    merged_config = deep_merge(provider_globals, config)
    agent = AgentSpec(provider=provider, system="", config=merged_config)
    prov = instantiate_provider(agent)

    system = "You are a rigorous QA evaluator. Return JSON only."
    prompt = f"""## Goal
{goal}

## Output to evaluate
{content}

## Your task
Evaluate the output against the goal. Be precise and critical.
Respond ONLY as JSON:
{{
  "status": "pass" | "fail" | "retry",
  "feedback": "specific, actionable feedback",
  "score": 0.0-1.0
}}"""

    raw = prov.complete(system, prompt)

    from superteam.core.loop import parse_verdict
    try:
        verdict = parse_verdict(raw, evaluator=prov, system=system)
        typer.echo(json.dumps(asdict(verdict), indent=2))
    except ValueError:
        typer.echo(raw)
