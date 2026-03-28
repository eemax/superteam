from __future__ import annotations

import json

import typer

from superteam.core.session import Session

sessions_app = typer.Typer(no_args_is_help=True)


@sessions_app.command("list")
def sessions_list_command(
    status: str | None = typer.Option(None, "--status", help="Filter by status (running, done, failed, paused)."),
    format: str = typer.Option("text", "--format", help="Output format: text or json."),
) -> None:
    """List all sessions, optionally filtered by status."""
    sessions = Session.list_all(status=status)
    metas = [s.load_meta() for s in sessions]
    metas.sort(key=lambda m: m.created_at, reverse=True)

    if format == "json":
        typer.echo(json.dumps([m.__dict__ for m in metas], indent=2))
        return

    if not metas:
        typer.echo("No sessions found.")
        return

    for meta in metas:
        typer.echo(
            f"{meta.session_id}\t{meta.status}\titerations={meta.iterations}\t"
            f"pipeline={meta.pipeline or '-'}"
        )
