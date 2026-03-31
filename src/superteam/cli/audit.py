from __future__ import annotations

import os
import sys

import typer


def audit_command(
    goal: str = typer.Option(..., "--goal", help="Goal to evaluate against."),
    module: str = typer.Option(..., "--module", help="Auditor module name."),
    model: str | None = typer.Option(None, "--model", help="Override module model."),
) -> None:
    """Run an auditor module on piped input. Usage: cat output.txt | superteam audit --goal '...' --module codex"""
    if sys.stdin.isatty():
        typer.echo("Pipe content to stdin. Example: cat output.txt | superteam audit --goal '...'", err=True)
        raise typer.Exit(1)

    content = sys.stdin.read()

    from superteam.runtime.pipeline import _module_registry, AgentSpec, instantiate_module
    from superteam.runtime.config import load_global_config, deep_merge

    registry = _module_registry()
    if module not in registry:
        supported = ", ".join(sorted(registry))
        typer.echo(f"Unknown module: {module}. Available: {supported}", err=True)
        raise typer.Exit(1)

    global_cfg = load_global_config()
    module_globals = global_cfg.get("modules", {}).get(module, {})
    config: dict = {}
    if model:
        config["model"] = model
    merged_config = deep_merge(module_globals, config)
    agent = AgentSpec(module=module, system="", config=merged_config)
    runtime = instantiate_module(agent)
    if "auditor" not in set(runtime.capabilities()):
        typer.echo(f"Module '{module}' does not support the auditor role.", err=True)
        raise typer.Exit(1)

    system = "You are a rigorous QA auditor. Return only the canonical Markdown audit report."
    prompt = f"""## Goal
{goal}

## Output to evaluate
{content}

## Your task
Evaluate the output against the goal as a software engineering audit. Be precise and critical.
"""

    from superteam.core.loop import audit_report_format_instructions, parse_verdict

    raw = runtime.run("auditor", system, prompt + "\n" + audit_report_format_instructions(), cwd=os.getcwd())

    try:
        verdict = parse_verdict(raw, auditor=runtime, system=system)
        typer.echo(verdict.to_markdown())
    except ValueError as exc:
        typer.echo(f"Could not parse auditor audit report: {exc}", err=True)
        typer.echo(raw, err=True)
        raise typer.Exit(1)
