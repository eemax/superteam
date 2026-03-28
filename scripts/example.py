#!/usr/bin/env -S uv run --script
# /// script
# dependencies = ["superteam", "anthropic"]
# ///

from superteam import ClaudeAPIProvider, ClaudeCodeProvider, LoopConfig, LoopState, Observer, Session, run_loop


session = Session.create(builder_provider="claude_code", eval_provider="claude_api", pipeline="script")
observer = Observer(session=session, stdout=True)

initial = LoopState(
    session_id=session.id,
    goal="Write a Python CLI tool that converts JSON to CSV",
    plan="1. Parse args 2. Read stdin JSON 3. Write CSV to stdout 4. Handle errors",
)

final = run_loop(
    ClaudeCodeProvider(),
    ClaudeAPIProvider(),
    initial,
    config=LoopConfig(max_iterations=3),
    observer=observer,
    session=session,
)

print(final.output)
