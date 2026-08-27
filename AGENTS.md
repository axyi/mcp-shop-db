# mcp-shop-db — agent rules

Read-only stdio MCP server over the shop.db SQLite database (course assignment 2).

Standards summary (self-contained): SDD — the spec is the contract; atomic commits (one prompt → one commit); review in a clean context; deterministic gates before done.
(SDD, atomic commits, model sizing, clean-context review, worktrees).

## Stack

- Language: Python >= 3.12, environment managed by **uv**
- Frameworks/libs: `mcp` Python SDK (FastMCP) for the server; `sqlite3` from the
  standard library for database access — no ORM, no other runtime dependencies
- Tooling: uv (lockfile-pinned), pytest, ruff

## Project layout

- `server.py` — the whole MCP server implementation (single file, per spec)
- `smoke_stdio.py` — standalone stdio smoke client: spawns the server over
  stdio, performs the handshake and one tool call, exits non-zero on failure
- `tests/` — pytest suite
- `data/shop.db` — committed SQLite fixture, **read-only**: never write to it,
  migrate it, or regenerate it; open it read-only from the server
- `docs/` — spec, prompt log, reports, token accounting

Context boundaries: agents work inside this repository only. Never read or edit
anything above the repository root.

## Commit format

- Conventional commits: `feat:`, `fix:`, `docs:`, `test:`, `refactor:`, `chore:`.
- **One prompt → one commit.** Reference the prompt file in the body:
  `(prompt: docs/prompts/NN-<slug>.md)`.
- Never mix results of different prompts in one commit or MR.

## Branch strategy

- One task → one branch: `feat/<slug>`, `fix/<slug>`, `docs/<slug>`.
- Parallel agent work: **one git worktree per agent**, merge via MR; never two
  agents in one working tree.

## Gates — run before reporting success

All four must exit 0, run in this order:

```bash
uv sync --locked
uv run --locked ruff check .
uv run --locked pytest
uv run --locked python smoke_stdio.py
```

## go protocol

`go docs/spec/spec-v0.md` is a standing instruction meaning: **execute that spec
end-to-end, following its own Execution contract section.** Concretely:

- run the gate commands above **verbatim** — same commands, same order, no
  substitutions, no "equivalent" invocations;
- on a failing gate, use the bounded fix loop defined in the spec (fixed maximum
  number of iterations); when the budget is exhausted, stop and report instead
  of retrying;
- log every prompt sent to an LLM as its own file in `docs/prompts/`, and record
  tokens/cost in `docs/llm-usage.md`;
- report the task as done only when every gate is green.

The spec is the contract. Where the spec and this file disagree, stop and ask.

## Review

Code review is performed by the `code-reviewer` subagent
(`.claude/agents/code-reviewer.md`) in its own clean context — never
self-review in the writing context.

## Reporting

Every prompt sent to an LLM is logged in `docs/prompts/` (one file per
prompt), tokens/cost in `docs/llm-usage.md`, run results in `docs/reports/`.
Every prompt sent to an LLM is logged in `docs/prompts/` (one file per prompt), tokens/cost in `docs/llm-usage.md`, run reports in `docs/reports/`.

## Secrets

Secrets live in `.env` (git-ignored). Never write secrets into code, docs,
prompts, or reports.
