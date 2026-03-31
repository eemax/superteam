# Markdown Audit Verdict Cutover

- Replace evaluator JSON verdicts with canonical Markdown audit reports using YAML frontmatter.
- Require frontmatter fields: `status`, `audit_verdict`, `score`, `next_steps`, and `metadata`.
- Require the audit body sections in order: Context, Verdict, Findings Summary, Findings, Recommendations, Audit Details, Scope Exclusions.
- Update loop behavior so only `status=pass` can complete, with `min_score` acting as an additional gate rather than an override.
- Feed the next builder attempt both the previous audit report and the structured `next_steps`.
- Keep the session file layout, but persist the richer verdict payloads inside the existing checkpoint files.
- Remove `write-and-critique` and update docs/tests so the built-in surface is code review and QA only.
