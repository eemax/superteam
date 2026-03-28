from __future__ import annotations

import typer

from .audit import audit_command
from .result import result_command
from .run import run_command
from .sessions import sessions_app
from .status import status_command
from .watch import watch_command


app = typer.Typer(no_args_is_help=True)
app.command("run")(run_command)
app.command("watch")(watch_command)
app.command("status")(status_command)
app.command("result")(result_command)
app.command("audit")(audit_command)
app.add_typer(sessions_app, name="sessions")


def main() -> None:
    app()


if __name__ == "__main__":
    main()
