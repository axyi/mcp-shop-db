# Project plan — mcp-shop-db

Course assignment 2: a read-only stdio MCP server over the bundled SQLite
database `data/shop.db`, graded by connecting a live AI agent and asking it
8 control questions. Per assignment rules the implementation code must be
written by an AI coding agent — therefore the specification is the primary
authored artifact of this repository.

## Status

| Milestone | State |
|---|---|
| Repository scaffold | done |
| `docs/spec/spec-v0.md` (implementation spec, 82 requirements) | done — reviewed, gate passed (0 high/medium findings) |
| Implementation (`server.py`, tests, smoke) | **pending — launched by `go docs/spec/spec-v0.md`** |
| Submission (README complete, agent config attached) | pending implementation |

## How the implementation run works

An AI agent is started with the single instruction `go docs/spec/spec-v0.md`.
The spec opens with an Execution contract: work from the repo root, create
the files listed in its file tree, follow the tests-first implementation
order, run the acceptance gates verbatim, at most 5 repair-and-rerun cycles,
then produce the report from the spec's template (or stop with its blocker
template). Every prompt sent to an LLM is logged under `docs/prompts/`;
token/cost accounting is appended to `docs/llm-usage.md`.

## Acceptance gates (from the spec, verbatim)

```bash
uv sync --locked
uv run --locked ruff check .
uv run --locked pytest
uv run --locked python smoke_stdio.py
```

## Key design decisions (fixed in the spec)

- Exactly 3 tools: `list_tables`, `describe_table`, `read_query`.
- Positive SQL policy: a single `SELECT` / `WITH … SELECT` only; defense in
  depth via read-only URI + `PRAGMA query_only=ON` + a SQLite authorizer
  (exact action-constant table in-spec) + per-invocation connections.
- Resource bounds: 2 s query budget, ≤200 rows + truncation flag, byte caps
  per cell and per envelope.
- `mcp==2.1.1` pinned; the SDK's `FastMCP` → `MCPServer` rename is stated
  normatively and all skeletons in the spec were proven by real runs.
- The database is a committed synthetic fixture (SHA-256 pinned in-spec);
  the evaluation checklist includes the two data traps (no country data;
  all orders dated 2026).
