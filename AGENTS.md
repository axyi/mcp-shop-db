# mcp-shop-db — agent rules

Read-only stdio MCP server over the shop.db SQLite database (course assignment 2).

Standards summary (self-contained): SDD — the spec is the contract; atomic commits (one prompt → one commit); review in a clean context; deterministic gates before done.

## Spec

SDD: implementation task → spec first (`docs/spec/spec-vN.md`); the spec is
the contract.

**Spec drift:** architecture/tests/interfaces change → update
`docs/spec/spec-vN.md` same commit.

## Stack

- Language: Python 3.13 (pinned via .python-version; requires-python ">=3.12,<3.14"), environment managed by **uv**
- Frameworks/libs: `mcp` Python SDK (MCPServer, formerly FastMCP) for the
  server; `sqlite3` from the
  standard library for database access — no ORM, no other runtime dependencies
- Tooling: uv (lockfile-pinned), pytest, ruff
- NEVER add dependencies beyond the allowed list without asking.

## Project layout

- `server.py` — the whole MCP server implementation (single file, per spec)
- `smoke_stdio.py` — standalone stdio smoke client: spawns the server over
  stdio, performs the handshake and one tool call, exits non-zero on failure
- `tests/` — pytest suite
- `data/shop.db` — committed SQLite fixture, **read-only**: NEVER write to it,
  migrate it, or regenerate it; open it read-only from the server
- `docs/` — spec, prompt log, reports, token accounting

Context boundaries: agents work inside this repository only. NEVER read or edit
anything above the repository root.

## Commit format

- Conventional commits: `feat:`, `fix:`, `docs:`, `test:`, `refactor:`, `chore:`.
- **One prompt → one commit.** Reference the prompt file in the body:
  `(prompt: docs/prompts/NN-<slug>.md)`.
- NEVER mix results of different prompts in one commit or MR.
<!-- SYNC: canonical text lives in standards/workflow.md §6 (lab repo); this copy is intentionally self-contained -->

## Branch strategy

- One task → one branch: `feat/<slug>`, `fix/<slug>`, `docs/<slug>`.
- Exception: a single-agent run implementing a whole spec end-to-end may
  commit directly to `main`; branches are for parallel or partial work.
- Parallel agent work: **one git worktree per agent**, merge via MR; NEVER two
  agents in one working tree.

## Gates — run before reporting success

<!-- DEFAULT STACK (Python/uv). Non-Python: replace this whole block with the project's real commands. -->

All four MUST exit 0, run in this order:

```bash
uv sync --locked
uv run --locked ruff check .
uv run --locked pytest
uv run --locked python smoke_stdio.py
```

## go protocol

<!-- SYNC: canonical text lives in standards/workflow.md §9 (lab repo); this copy is intentionally self-contained -->

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
(`.claude/agents/code-reviewer.md`) in its own clean context — NEVER
self-review in the writing context.

## Reporting

Every prompt sent to an LLM is logged in `docs/prompts/` (one file per
prompt), tokens/cost in `docs/llm-usage.md`, run results in `docs/reports/`.

After each run report, generate `docs/reports/tg-post-vN.md` — a
ready-to-paste Telegram post, written in **Russian**: constraints → result →
metrics (executor model — always named; spec tokens, prompts, first-run,
bugs, tokens in/out, cost — when the harness does not expose tokens/cost,
keep that note and add an estimate at public API prices) → a
link to this project's GitHub repository
(https://github.com/axyi/mcp-shop-db). Under ~1500 characters.


## Secrets

Secrets live in `.env` (git-ignored). NEVER write secrets into code, docs,
prompts, or reports.
