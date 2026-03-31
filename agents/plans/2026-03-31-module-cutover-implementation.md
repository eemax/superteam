# 2026-03-31 Module Cutover Implementation

Refactor `superteam` from raw provider adapters to full builder/auditor modules only.

## Goals

- Replace provider terminology with module terminology across runtime, CLI, session metadata, docs, and tests.
- Remove thin raw-model integrations and keep only full CLI-backed modules plus deterministic test doubles.
- Add Codex and Claude Code as first-class modules and persist invocation records for every module call.

## Implementation Notes

- Runtime and pipeline config now use `module` keys and `[modules.<name>]` config sections.
- Session metadata stores `builder_module` and `auditor_module`.
- The loop records exact module inputs/outputs plus timing in `invocations/`.
- Built-in pipelines now use `claude_code` and `codex` only.
