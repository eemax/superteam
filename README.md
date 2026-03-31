# superteam

A Python 3.12+ harness for non-interactive builder/auditor loops across full agent modules.

## What's here

- **Core loop engine** — `step_once()` and `run_loop()` with artifact spilling, verdict parsing, and transient retry
- **File-backed sessions** — atomic persistence under `~/.superteam/sessions/`, append-only JSONL event logs, invocation records, and per-iteration checkpoints
- **Full module adapters** — Codex CLI and Claude Code CLI
- **YAML pipeline loader** — typed `PipelineSpec`, built-in pipelines as package resources
- **Global config** — `~/.superteam/config.toml` with deep-merge precedence (`global < pipeline < CLI`)
- **CLI** — `run`, `watch`, `status`, `result`, `sessions list`, `audit`
- **Deterministic testing** — fake builder/auditor modules, `SUPERTEAM_HOME` isolation, no live model APIs required

## Quick start

```bash
uv sync --extra cli --extra dev
```

Install the external CLIs you want to use separately:

- `codex`
- `claude`

## Built-in pipelines

| Pipeline | Builder | Auditor | Description |
|----------|---------|---------|-------------|
| `code-review-loop` | `claude_code` | `codex` | Builder writes code, auditor produces a strict software review |
| `qa-loop` | `codex` | `claude_code` | Cross-module QA audit for software engineering work |

```bash
superteam run code-review-loop --goal "Write a Python CLI that converts JSON to CSV"
superteam run qa-loop --goal "Audit this API client for retry, timeout, and auth-handling issues"
```

## CLI commands

```bash
superteam run <pipeline> --goal "..." [--plan "..."] [--detach]
superteam watch <session-id> [--format pretty|json] [--follow/--no-follow]
superteam status <session-id> [--format json|text]
superteam result <session-id> [--format text|json]
superteam sessions list [--status done|running|failed] [--format text|json]
superteam audit --goal "..." --module codex [--model ...]  # pipe content to stdin
```

Auditors return a canonical Markdown audit report with YAML frontmatter:

```markdown
---
status: retry
audit_verdict: PASS WITH CONDITIONS
score: 0.82
next_steps:
  - Add regression tests for token expiry
metadata: {}
---

# Agent Audit

## 1. Context
...
```

## Session model

Each session creates `~/.superteam/sessions/<id>/` with:

- `meta.json` — status, timestamps, pipeline, builder/auditor module names
- `state.json` — full `LoopState` with iteration history
- `events.jsonl` — append-only event log
- `iterations/` — per-iteration state and verdict snapshots
- `invocations/` — persisted module call records with timing, prompts, outputs, and spill refs
- `artifacts/` — spilled outputs and large invocation payloads
- `run.pid` — PID for detached runs

Sessions use explicit lifecycle: `Session.create()` for new, `Session.open()` for existing.

## Module support

| Module | Type | Dependency |
|--------|------|------------|
| `codex` | CLI runtime | `codex` binary |
| `claude_code` | CLI runtime | `claude` binary |
| `fake_builder` | Testing | — |
| `fake_auditor` | Testing | — |

## Library usage

```python
from superteam import LoopConfig, LoopState, Observer, run_loop
from superteam.modules.testing import StaticAuditorModule, StaticAuditorModuleConfig, StaticBuilderModule, StaticBuilderModuleConfig

builder = StaticBuilderModule(StaticBuilderModuleConfig(outputs=["hello world"]))
auditor = StaticAuditorModule(
    StaticAuditorModuleConfig(
        responses=[
            {
                "status": "pass",
                "audit_verdict": "PASS",
                "score": 1.0,
                "next_steps": [],
                "metadata": {},
                "feedback": "Looks good.",
            }
        ]
    )
)

state = LoopState(session_id="st-example", goal="Build something", plan="Do it")
final = run_loop(
    builder,
    auditor,
    state,
    config=LoopConfig(max_iterations=3),
    builder_module_name="fake_builder",
    auditor_module_name="fake_auditor",
)
```

## Global config

Optional `~/.superteam/config.toml`:

```toml
[modules.codex]
model = "gpt-5-codex"

[modules.claude_code]
model = "claude-opus-4-1"

[loop]
max_iterations = 10
```

Precedence: CLI args > pipeline YAML > global config.

## Testing

```bash
uv run pytest
```

Tests use `SUPERTEAM_HOME` isolation and deterministic fake modules. Live CLI smoke tests are opt-in via `SUPERTEAM_RUN_LIVE_SMOKE=1`.
