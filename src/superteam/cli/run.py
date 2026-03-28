from __future__ import annotations

from pathlib import Path
import json
import os
import subprocess
import sys

import typer

from superteam.core.contracts import LoopState
from superteam.core.loop import run_loop
from superteam.core.observe import Observer
from superteam.core.session import Session
from superteam.runtime.pipeline import load_pipeline, prepare_run


def run_command(
    pipeline: str = typer.Argument(..., help="Pipeline path or built-in pipeline name."),
    goal: str | None = typer.Option(None, "--goal", help="Goal for the builder/evaluator loop."),
    plan: str | None = typer.Option(None, "--plan", help="Execution plan. Defaults to goal."),
    detach: bool = typer.Option(False, "--detach", help="Run in the background and return the session id."),
    session_id: str | None = typer.Option(None, "--_session-id", hidden=True),
    background: bool = typer.Option(False, "--_background", hidden=True),
) -> None:
    pipeline_ref = _resolve_pipeline_ref(pipeline)

    if detach and not background:
        spec = load_pipeline(pipeline_ref)
        resolved_goal = goal or spec.input_defaults.get("goal")
        if not resolved_goal:
            raise typer.BadParameter("A goal is required either via --goal or pipeline input.goal")
        resolved_plan = plan or spec.input_defaults.get("plan") or resolved_goal
        session = Session.create(
            builder_provider=spec.builder.provider,
            eval_provider=spec.evaluator.provider,
            pipeline=spec.name,
        )
        process = _spawn_detached_run(session.id, pipeline_ref, resolved_goal, resolved_plan)
        session.write_run_pid(process.pid)
        typer.echo(session.id)
        return

    try:
        prepared = prepare_run(pipeline_ref, goal=goal, plan=plan)
    except ValueError as exc:
        raise typer.BadParameter(str(exc)) from exc

    session = (
        Session.open(session_id)
        if background and session_id is not None
        else Session.create(
            session_id=session_id,
            builder_provider=prepared.builder_provider_name,
            eval_provider=prepared.evaluator_provider_name,
            pipeline=prepared.pipeline_name,
        )
    )
    if background:
        session.write_run_pid(os.getpid())

    observer = Observer(session=session, stdout=not background)
    initial = LoopState(session_id=session.id, goal=prepared.goal, plan=prepared.plan)

    try:
        final = run_loop(
            prepared.builder,
            prepared.evaluator,
            initial,
            config=prepared.loop_config,
            observer=observer,
            session=session,
            builder_system=prepared.builder_system,
            evaluator_system=prepared.evaluator_system,
        )
    except Exception as exc:
        observer.emit("error", {"step": "run", "message": str(exc)})
        session.finish("failed")
        if background:
            return
        raise typer.Exit(code=1) from exc

    if background:
        return

    typer.echo(session.id)
    typer.echo(session.resolve_output_text(final))


def _resolve_pipeline_ref(pipeline: str) -> str:
    candidate = Path(pipeline).expanduser()
    if candidate.exists():
        return str(candidate.resolve())
    return pipeline


def _spawn_detached_run(session_id: str, pipeline: str, goal: str, plan: str) -> subprocess.Popen:
    package_root = Path(__file__).resolve().parents[2]
    env = os.environ.copy()
    existing_path = env.get("PYTHONPATH")
    env["PYTHONPATH"] = str(package_root) if not existing_path else os.pathsep.join([str(package_root), existing_path])

    cmd = [
        sys.executable,
        "-m",
        "superteam.cli.main",
        "run",
        pipeline,
        "--goal",
        goal,
        "--plan",
        plan,
        "--_background",
        "--_session-id",
        session_id,
    ]
    return subprocess.Popen(
        cmd,
        cwd=os.getcwd(),
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )
