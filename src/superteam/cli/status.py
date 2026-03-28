from __future__ import annotations

import json

import typer

from superteam.core.session import Session


def status_command(
    session_id: str = typer.Argument(..., help="Session id."),
    format: str = typer.Option("json", "--format", help="Output format."),
) -> None:
    session = Session.open(session_id)
    meta = session.load_meta()
    state = session.load_state_optional()
    payload = {
        "session_id": meta.session_id,
        "status": meta.status,
        "iteration": state.iteration if state is not None else meta.iterations,
        "final_score": meta.final_score,
        "pipeline": meta.pipeline,
        "builder_provider": meta.builder_provider,
        "eval_provider": meta.eval_provider,
    }
    pid = session.load_run_pid()
    if pid is not None:
        payload["pid"] = pid

    if format == "json":
        typer.echo(json.dumps(payload, indent=2))
    elif format == "text":
        parts = [f"{key}={value}" for key, value in payload.items() if value is not None]
        typer.echo(" ".join(parts))
    else:
        raise typer.BadParameter("Supported formats are json and text")
