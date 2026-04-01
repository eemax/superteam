# AGENTS.md

## Purpose

`superteam` is a Python 3.12+ harness for non-interactive builder/evaluator agent loops. Keep changes deterministic, testable, and easy to reason about without requiring live model calls during normal development.

## Repo Map

- `src/superteam/core/`: loop engine, state contracts, observer, and session persistence
- `src/superteam/runtime/`: global config loading, pipeline parsing, provider instantiation
- `src/superteam/providers/`: provider adapters plus testing doubles
- `src/superteam/cli/`: Typer commands for run/watch/status/result/sessions/audit
- `src/superteam/pipelines/`: built-in YAML pipeline specs
- `tests/`: unit and smoke coverage
- `docs/`: maintained project documentation
- `agents/plans/`: implementation plans, rollout notes, and scoped task breakdowns
- `agents/audits/`: code review findings, QA notes, and follow-up audits

## Working Agreements

- Start with `README.md` and `docs/architecture.md` before changing shared code.
- Prefer deterministic tests that use fake/static providers instead of live services.
- Treat `LoopState`, `Verdict`, `SessionMeta`, and the on-disk session layout as stable contracts.
- Keep CLI behavior, built-in pipelines, and docs aligned. If one changes, review the others.
- Make small, coherent edits. Avoid mixing unrelated refactors into functional work.

## Change Guides

### Core loop changes

- Main entry points live in `src/superteam/core/loop.py`.
- If you change prompt construction, verdict parsing, retry behavior, or stop conditions, update tests that cover loop outcomes and failure modes.
- If output spilling behavior changes, review both `OUTPUT_INLINE_LIMIT` handling and session artifact reads.

### Session and state changes

- Session persistence lives in `src/superteam/core/session.py`.
- State and verdict schemas live in `src/superteam/core/contracts.py`.
- Any schema or layout change should include backward-compatibility thinking, test coverage, and a docs update in `docs/architecture.md`.

### Pipeline and config changes

- Pipeline loading and provider instantiation live in `src/superteam/runtime/pipeline.py`.
- Global config merge logic lives in `src/superteam/runtime/config.py`.
- When adding a provider, wire it into the provider registry, package exports, docs, and tests.

### CLI changes

- CLI entrypoints live under `src/superteam/cli/`.
- New commands should include at least one focused test for argument handling or command behavior.
- Keep command help text and README examples in sync.

## Planning And Audit Trail

- For multi-step work, create a dated markdown note in `agents/plans/`.
- For reviews, QA passes, or post-change concerns, capture findings in `agents/audits/`.
- Suggested filenames:
  - `agents/plans/2026-03-28-session-resume-plan.md`
  - `agents/audits/2026-03-28-provider-smoke-audit.md`

## Validation

- Install deps: `uv sync --extra dev`
- Run full tests: `uv run pytest`
- Run a focused test file: `uv run pytest tests/test_pipeline.py`
- Exercise the CLI locally: `uv run superteam run code-review-loop --goal "..."`

## Documentation Expectations

- Update `README.md` for user-facing behavior changes.
- Update `docs/architecture.md` for structural or lifecycle changes.
- Prefer short, operational docs over broad aspirational prose.
