from __future__ import annotations

import json

import typer

from superteam.core.session import Session


def result_command(
    session_id: str = typer.Argument(..., help="Session id."),
    format: str = typer.Option("text", "--format", help="text or json"),
) -> None:
    session = Session.open(session_id)
    meta = session.load_meta()
    state = session.load_state_optional()
    if state is None:
        raise typer.Exit(code=1)

    if format == "text":
        typer.echo(session.resolve_output_text(state))
        return
    if format == "json":
        typer.echo(
            json.dumps(
                {
                    "meta": meta.__dict__,
                    "state": state.to_dict(),
                },
                indent=2,
            )
        )
        return
    raise typer.BadParameter("Supported formats are text and json")
