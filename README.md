# superteam

A Python 3.12+ harness for non-interactive builder/evaluator loops focused on software-engineering code review and QA audits.

## What's here

- **Core loop engine** — `step_once()` and `run_loop()` with artifact spilling, verdict parsing, and transient retry
- **File-backed sessions** — atomic persistence under `~/.superteam/sessions/`, append-only JSONL event logs
- **Provider adapters** — Claude API, Claude Code (subprocess), OpenRouter
- **YAML pipeline loader** — typed `PipelineSpec`, built-in pipelines as package resources
- **Global config** — `~/.superteam/config.toml` with deep-merge precedence (global < pipeline < CLI)
- **CLI** — `run`, `watch`, `status`, `result`, `sessions list`, `audit`
- **Deterministic testing** — fake providers, `SUPERTEAM_HOME` isolation, no live API needed

## Quick start

```bash
uv sync --extra cli --extra claude --extra dev
```

## Built-in pipelines

| Pipeline | Builder | Evaluator | Description |
|----------|---------|-----------|-------------|
| `code-review-loop` | claude_code | claude_api | Builder writes code, evaluator produces a senior-review audit |
| `qa-loop` | claude_code | openrouter | Cross-provider QA audit for software engineering work |

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
superteam audit --goal "..." --provider claude_api [--model ...]  # pipe content to stdin
```

Evaluators return a canonical Markdown audit report with YAML frontmatter:

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
- `meta.json` — status, timestamps, provider names
- `state.json` — full `LoopState` with history
- `events.jsonl` — append-only event log
- `iterations/` — per-iteration state and verdict snapshots
- `artifacts/` — spilled outputs (> 8KB)
- `workspace/` — working directory for subprocess providers

Sessions use explicit lifecycle: `Session.create()` for new, `Session.open()` for existing.

## Provider support

| Provider | Type | Dependency | Env var |
|----------|------|------------|---------|
| `claude_api` | Anthropic SDK | `anthropic` | `ANTHROPIC_API_KEY` |
| `claude_code` | Subprocess | `claude` CLI | — |
| `openrouter` | HTTP API | `httpx` | `OPENROUTER_API_KEY` |
| `fake_builder` | Testing | — | — |
| `fake_evaluator` | Testing | — | — |

Install provider dependencies via extras:
```bash
uv sync --extra claude       # claude_api
uv sync --extra openrouter   # openrouter
```

## Library usage

```python
from superteam import LoopState, LoopConfig, Observer, run_loop
from superteam.providers.testing import StaticBuilderProvider, StaticBuilderConfig

builder = StaticBuilderProvider(StaticBuilderConfig(outputs=["hello world"]))
evaluator = ...  # any object with complete(system, prompt, state) -> canonical audit markdown

state = LoopState(session_id="st-example", goal="Build something", plan="Do it")
final = run_loop(builder, evaluator, state, config=LoopConfig(max_iterations=3))
```

## Global config

Optional `~/.superteam/config.toml`:

```toml
[providers.openrouter]
api_key = "sk-or-..."
model = "openai/gpt-4o"

[loop]
max_iterations = 10
```

Precedence: CLI args > pipeline YAML > global config.

## Testing

```bash
uv run pytest
```

Tests use `SUPERTEAM_HOME` isolation — no live API calls needed. Live smoke tests are opt-in via `SUPERTEAM_RUN_LIVE_SMOKE=1`.
