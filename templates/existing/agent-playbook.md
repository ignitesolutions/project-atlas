# Agent Playbook

Read `project-overview.md`, `architecture.md`, `code-map.md`, `operations.md`, and
`open-questions.md` before making changes. Check `atlas.json` for lifecycle state, freshness,
source evidence, and generated-section ownership.

Preserve all hand-authored text outside `<!-- project-atlas:generated:* -->` blocks. After a
durable change, run focused maintenance with `--paths`, `--changed-since`, or `--domain`.
Formatting-only, temporary debug, and reverted changes do not require Atlas maintenance.

Complete semantic contract criteria with supported prose and repository-relative evidence paths.
Use `unknown` with an impact note when evidence cannot resolve a criterion; never mark it complete
from generated candidates alone.

Use specialized documents only when they exist and are relevant. Record an architectural
decision or handoff only when the work creates a durable decision or needs continuation context.
Never record secret values (passwords, keys, tokens, connection strings) — names, locations, and access patterns only.

Before reporting Atlas completion, run semantic verification. Structure or evidence success
alone does not mean human interpretation is complete.

## Decisions

Architectural decisions are recorded in `project-atlas/decisions/`. Check that directory before
reversing or replacing an established pattern. Add a new decision record — copy
`decisions/TEMPLATE.md` to `decisions/000X-short-name.md` — when you make a choice with lasting
impact: adopting or rejecting a library, changing a data model, picking an auth or session
strategy, or diverging from an existing convention. Do not record routine or easily-reversible
changes.
