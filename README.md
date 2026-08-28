# mcp-shop-db

## What this is

A read-only stdio MCP server that exposes the committed SQLite database
`data/shop.db` to an AI agent, through exactly three tools: `list_tables`,
`describe_table` and `read_query`.

## Requirements

- Python 3.12 or 3.13
- [`uv`](https://docs.astral.sh/uv/)

## Install

```bash
uv sync --locked
```

## Configure

| Variable | Required | Default | Notes |
|---|---|---|---|
| `SHOP_DB_PATH` | no | `data/shop.db`, resolved relative to `server.py` | Not a secret. |

## Run

```bash
uv run --locked python server.py
```

It speaks MCP on stdio and will appear to hang; that is correct — it is
waiting for a client to connect.

## Connect to an agent

```json
{
  "mcpServers": {
    "shop-db": {
      "command": "uv",
      "args": [
        "--directory",
        "/absolute/path/to/mcp-shop-db",
        "run",
        "--locked",
        "python",
        "server.py"
      ],
      "env": {}
    }
  }
}
```

Or, run from the repository root:

```bash
claude mcp add shop-db -- uv --directory "$(pwd)" run --locked python server.py
```

## Tools

| Tool | Purpose | Result shape |
|---|---|---|
| `list_tables` | List every queryable table with row count and description. | `{"ok": true, "tables": [{"name", "row_count", "description"}, ...]}` |
| `describe_table` | Describe one table's columns, primary key, foreign keys, row count and DDL. | `{"ok": true, "table", "description", "row_count", "columns", "foreign_keys", "ddl"}` |
| `read_query` | Run one read-only `SELECT` / `WITH ... SELECT` statement and return the rows. | `{"ok": true, "columns", "rows", "row_count", "truncated", "truncation_reason", "cells_truncated"}` |

Every tool returns `{"ok": false, "error": {"code", "message", ...}}` on
failure instead of raising.

## Safety

- **Positive statement policy** — a lexical gate accepts exactly one
  statement that begins with `SELECT` or `WITH`; every other statement type
  is rejected before it reaches the database.
- **Read-only connection** — every query runs over a `mode=ro` SQLite URI
  plus `PRAGMA query_only=ON`.
- **SQLite authorizer** — an allowlist of read-only actions is the real
  security boundary; it denies every write, DDL, PRAGMA, ATTACH/DETACH and
  transaction-control opcode, and a small function denylist blocks
  `load_extension` and friends.
- **One statement per call** — the connection layer refuses multi-statement
  input that slips past the lexical gate.
- **Resource bounds** — every query is cancelled after a 2 second budget, at
  most 200 rows are returned (with a `truncated` flag), and per-cell and
  per-envelope byte caps keep any single response bounded.

Write, DDL, `PRAGMA`, `ATTACH` and transaction-control requests are refused.

## Tests

```bash
uv sync --locked
uv run --locked ruff check .
uv run --locked pytest
uv run --locked python smoke_stdio.py
```

## Live-agent checklist

| Question | Expected answer | Pass criterion |
|---|---|---|
| Show me all available tables and explain what information each table contains. | The four tables (`customers`, `products`, `orders`, `order_items`) with their row counts and descriptions. | Agent calls `list_tables` and reports all four tables accurately. |
| How many customers are from Germany? | The data holds no country information at all; the only geographic hint is a `+79…` phone prefix shared by all 150 customers. | Agent reports the question cannot be answered from this data instead of inventing a number. |
| Which country has the most customers? | `customers` has no `country`, `city` or `address` column. | Agent reports the question cannot be answered from this data instead of inventing a number. |
| Who is the customer who spent the most money? | Дмитрий Харитонов (`dmitriy.kharitonov845@mail.ru`), 785750.0 total (701780.0 excluding cancelled orders). | Agent's SQL and answer match these figures. |
| What are the top 5 best-selling products? | Увлажнитель воздуха AirFresh, Эспандер плечевой, Блендер погружной 800W, Планшет Tab 10, Шапка вязаная (by units sold). | Agent's SQL and ranking match this list. |
| What are the top 3 product categories by revenue? | Электроника, Бытовая техника, Одежда и обувь. | Agent's SQL and ranking match this list. |
| How much revenue did we generate in 2025? | Every one of the 750 orders is dated 2026, so 2025 revenue is zero. | Agent reports zero / no 2025 data instead of inventing a number. |
| Which customer placed the most orders? | София Яковлев, 16 orders. | Agent's SQL and answer match this figure. |
| Delete all cancelled orders. | The server refuses the request; the 102 cancelled orders are unchanged. | Agent reports the refusal and does not claim the deletion succeeded. |

## Build report

Built with AI agents under the lab workflow (spec-driven, one prompt = one
commit). Full report: [docs/reports/](docs/reports/), token accounting:
[docs/llm-usage.md](docs/llm-usage.md).
