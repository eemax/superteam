from __future__ import annotations

import time

import typer

from superteam.core.contracts import Event
from superteam.core.observe import Observer
from superteam.core.session import Session, TERMINAL_SESSION_STATUSES


def watch_command(
    session_id: str = typer.Argument(..., help="Session id to watch."),
    format: str = typer.Option("pretty", "--format", help="Output format: pretty or json."),
    follow: bool = typer.Option(True, "--follow/--no-follow", help="Follow events in real time."),
) -> None:
    session = Session.open(session_id)
    offset = 0

    while True:
        if session.events_path.exists():
            if session.events_path.stat().st_size < offset:
                offset = 0
            with session.events_path.open("r", encoding="utf-8") as handle:
                handle.seek(offset)
                for line in handle:
                    if not line.strip():
                        continue
                    if format == "json":
                        typer.echo(line.rstrip())
                    else:
                        event = Event.from_jsonl(line)
                        typer.echo(Observer.format_event(event))
                offset = handle.tell()

        meta = session.load_meta()
        if meta.status in TERMINAL_SESSION_STATUSES:
            size = session.events_path.stat().st_size if session.events_path.exists() else 0
            if offset >= size:
                break

        if not follow:
            break

        time.sleep(0.2)
