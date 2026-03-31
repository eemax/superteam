# Architecture

## Overview

`superteam` is an orchestration kernel for non-interactive builder/auditor loops. A pipeline selects two full agent modules, the runtime instantiates them, the core loop coordinates iterations, and the session layer persists state, artifacts, and invocation records on disk.

## Package Layout

- `src/superteam/core/`
  - `contracts.py`: dataclasses for `LoopState`, `Verdict`, `IterationRecord`, `InvocationRecord`, `SessionMeta`, and `Event`
  - `loop.py`: prompt assembly, verdict parsing, artifact spilling, invocation capture, retry logic, and loop termination
  - `modules.py`: protocol for full builder/auditor modules
  - `observe.py`: event emission to stdout and/or persisted JSONL logs
  - `session.py`: session directories, atomic writes, checkpoints, and invocation persistence
- `src/superteam/runtime/`
  - `config.py`: global config loading plus deep-merge helpers
  - `pipeline.py`: YAML pipeline loading, module registry, config resolution, and run preparation
- `src/superteam/modules/`
  - CLI-backed module packages for `codex` and `claude_code`
  - `testing.py` provides deterministic static builder/auditor fakes for tests
- `src/superteam/cli/`
  - Typer commands for `run`, `watch`, `status`, `result`, `sessions list`, and `audit`
- `src/superteam/pipelines/`
  - Built-in YAML pipeline specs shipped as package data

## Runtime Flow

```mermaid
flowchart TD
    A["CLI command"] --> B["runtime.pipeline.prepare_run()"]
    B --> C["Instantiate builder and auditor modules"]
    C --> D["Create or open Session"]
    D --> E["core.loop.run_loop()"]
    E --> F["Builder module runs"]
    F --> G["Optional artifact spill"]
    G --> H["Auditor module scores output"]
    H --> I["Session checkpoint + event log + invocation records"]
    I --> J{"Stop condition met?"}
    J -- No --> E
    J -- Yes --> K["Finalize session status"]
```

### `run` command path

1. `src/superteam/cli/run.py` resolves a pipeline reference and optional goal/plan overrides.
2. `prepare_run()` loads the pipeline YAML, merges global module config, and instantiates concrete module classes.
3. A `Session` is created or reopened for background execution.
4. `run_loop()` drives iterations until a passing audit or max-iteration policy is reached.
5. The final state is persisted, and the CLI prints the session id plus resolved output for foreground runs.

### `audit` command path

`src/superteam/cli/audit.py` skips the builder loop entirely. It reads piped content from stdin, instantiates a single auditor module, and emits the same canonical Markdown audit report parsed by the main loop.

## Core Data Model

### `LoopState`

The mutable state for a run. It carries:

- session identity
- goal and plan
- current iteration number
- latest output or spilled artifact reference
- previous audit report and next steps
- optional context payload
- iteration history

### `Verdict`

The auditor response contract is a canonical Markdown audit report with YAML frontmatter. The parsed verdict includes:

- `status`: `pass`, `fail`, or `retry`
- `audit_verdict`: `PASS`, `PASS WITH CONDITIONS`, or `FAIL`
- `score`: numeric quality/confidence score
- `next_steps`: structured follow-up actions for the next builder pass
- `metadata`: freeform machine-readable audit metadata
- `feedback`: the Markdown audit body with the seven required sections

### `InvocationRecord`

Each module call persists:

- module id and role
- iteration number and retry attempt
- cwd
- started/ended timestamps and duration
- exact system prompt, task prompt, final output, and any spill refs
- error text when a call fails

## Persistence Model

Sessions are file-backed under `SUPERTEAM_HOME` or `~/.superteam` by default.

Each session directory follows this shape:

```text
~/.superteam/sessions/<session-id>/
  meta.json
  state.json
  events.jsonl
  run.pid
  iterations/
    001.json
    001.verdict.json
  invocations/
    0001.json
    0002.json
  artifacts/
    001.artifact
    invocation-0001-output.txt
```

### Persistence rules

- Metadata and state writes are atomic.
- Event logs are append-only JSONL.
- Large builder outputs spill to `artifacts/` once they cross `OUTPUT_INLINE_LIMIT`.
- Large invocation payloads spill to `artifacts/` and remain linked from `invocations/`.
- `state.json` always represents the latest known loop state.

## Configuration And Pipelines

Pipelines are YAML specs that define:

- pipeline metadata
- loop configuration such as max iterations and retry policy
- builder module, system prompt, and module config
- auditor module, system prompt, and module config
- default input values such as `goal` and `plan`

Config precedence is:

`CLI args > pipeline YAML > global config (~/.superteam/config.toml)`

Global config is merged per module and for loop settings before modules are instantiated.

## Module Boundary

Modules are expected to expose:

- `run(role, system, prompt, state=None, cwd=None) -> str`
- `health() -> bool`
- `capabilities() -> set[str]`

The loop wraps modules to add:

- observer events
- transient retry handling
- persisted invocation records

## Testing Strategy

The test suite is designed to run without live model APIs.

- Use `src/superteam/modules/testing.py` for deterministic loop tests.
- Use `SUPERTEAM_HOME` isolation in tests that touch session persistence.
- Prefer focused tests around loop control flow, session layout, config merging, CLI behavior, and module command construction.

## Extension Checklist

### Adding a module

- Add the module package under `src/superteam/modules/`
- Export it from `src/superteam/modules/__init__.py`
- Register it in `src/superteam/runtime/pipeline.py`
- Document required external CLI/runtime dependencies in `README.md`
- Add focused tests and, if appropriate, a smoke test

### Changing session/state behavior

- Update `core/contracts.py` and/or `core/session.py`
- Review the on-disk session layout and CLI outputs
- Update architecture docs and tests that assert persisted layout

### Adding a built-in pipeline

- Add the YAML file under `src/superteam/pipelines/`
- Register the name in `BUILTIN_PIPELINES`
- Cover loading and defaults with tests
- Add user-facing documentation if the pipeline is intended for general use
