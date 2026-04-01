#!/usr/bin/env -S uv run --script
# /// script
# dependencies = ["superteam"]
# ///

from superteam import LoopConfig, LoopState, Observer, Session, run_loop
from superteam.modules.claude_code import ClaudeCodeConfig, ClaudeCodeModule
from superteam.modules.codex import CodexModule


session = Session.create(builder_module="claude_code", auditor_module="codex", pipeline="script")
observer = Observer(session=session, stdout=True)

initial = LoopState(
    session_id=session.id,
    goal="Write a Python CLI tool that converts JSON to CSV",
    plan="1. Parse args 2. Read stdin JSON 3. Write CSV to stdout 4. Handle errors",
)

final = run_loop(
    ClaudeCodeModule(ClaudeCodeConfig()),
    CodexModule(),
    initial,
    config=LoopConfig(max_iterations=3),
    observer=observer,
    session=session,
    builder_module_name="claude_code",
    auditor_module_name="codex",
)

print(final.output)
