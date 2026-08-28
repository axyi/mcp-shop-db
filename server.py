from __future__ import annotations

import json
import logging
import math
import os
import sqlite3
import sys
import time
import urllib.parse
from pathlib import Path
from typing import Annotated, Any

from mcp.server.mcpserver import MCPServer
from pydantic import Field

log = logging.getLogger("mcp-shop-db")


def setup_logging() -> None:
    """Send every log record to stderr. stdout carries protocol frames only."""
    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(logging.Formatter("%(levelname)s %(name)s: %(message)s"))
    log.handlers[:] = [handler]
    log.setLevel(logging.INFO)
    log.propagate = False


PROJECT_ROOT = Path(__file__).resolve().parent


def _resolve_db_path() -> Path:
    raw = os.environ.get("SHOP_DB_PATH", "").strip()
    candidate = Path(raw) if raw else Path("data/shop.db")
    if not candidate.is_absolute():
        candidate = PROJECT_ROOT / candidate
    return candidate.resolve()


DB_PATH = _resolve_db_path()

TABLE_DESCRIPTIONS = {
    "customers": "Registered shop customers: name, unique email, optional phone, signup timestamp.",
    "products": "Product catalogue: name, category, unit price, stock quantity, creation timestamp.",
    "orders": "Customer orders: owning customer, order timestamp, lifecycle status, order total.",
    "order_items": "Line items of an order: product, quantity ordered, unit price at order time.",
}
NO_DESCRIPTION = "No description available."

LIST_TABLES_QUERY = (
    "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
)

QUERY_BUDGET_SECONDS = 2.0
PROGRESS_HANDLER_INSTRUCTIONS = 1000
MAX_FETCH_ROWS = 201
MAX_RETURN_ROWS = 200
MAX_CELL_BYTES = 4096
MAX_ENVELOPE_BYTES = 262144
RESERVED_METADATA_BYTES = 4096
BLOB_PREVIEW_BYTES = 64

TRUNCATION_MARKER = "…[truncated]"

ALLOWED_ACTIONS = frozenset(
    {
        sqlite3.SQLITE_SELECT,
        sqlite3.SQLITE_READ,
        sqlite3.SQLITE_FUNCTION,
        sqlite3.SQLITE_RECURSIVE,
    }
)
DENIED_FUNCTIONS = frozenset(
    {
        "load_extension",
        "readfile",
        "writefile",
        "edit",
        "fts3_tokenizer",
        "zipfile",
        "sqlar_compress",
        "sqlar_uncompress",
    }
)


def dumps(obj: Any) -> str:
    return json.dumps(obj, ensure_ascii=False, allow_nan=False, separators=(",", ":"))


def ok(payload: dict) -> str:
    return dumps({"ok": True, **payload})


def err(code: str, message: str, **extra: Any) -> str:
    log.warning("tool error: code=%s message=%s", code, message)
    return dumps({"ok": False, "error": {"code": code, "message": message, **extra}})


def _quote_ident(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


def _authorizer(action: int, arg1, arg2, dbname, source) -> int:
    if action == sqlite3.SQLITE_FUNCTION:
        if arg2 is not None and arg2.lower() in DENIED_FUNCTIONS:
            return sqlite3.SQLITE_DENY
        return sqlite3.SQLITE_OK
    if action in ALLOWED_ACTIONS:
        return sqlite3.SQLITE_OK
    return sqlite3.SQLITE_DENY


def open_connection(*, restricted: bool) -> sqlite3.Connection:
    if not DB_PATH.is_file():
        raise FileNotFoundError(f"Database not found at {DB_PATH}")

    uri = "file:" + urllib.parse.quote(str(DB_PATH), safe="/") + "?mode=ro"
    conn = sqlite3.connect(uri, uri=True, timeout=5.0, isolation_level=None)
    conn.execute("PRAGMA query_only=ON")

    deadline = time.monotonic() + QUERY_BUDGET_SECONDS
    conn.set_progress_handler(
        lambda: 1 if time.monotonic() > deadline else 0, PROGRESS_HANDLER_INSTRUCTIONS
    )

    if restricted:
        conn.set_authorizer(_authorizer)

    return conn


def _strip_comments(sql: str) -> str:
    result = []
    i = 0
    n = len(sql)
    while i < n:
        two = sql[i : i + 2]
        if two == "--":
            j = sql.find("\n", i)
            if j == -1:
                break
            i = j + 1
            continue
        if two == "/*":
            j = sql.find("*/", i + 2)
            if j == -1:
                break
            i = j + 2
            continue
        result.append(sql[i])
        i += 1
    return "".join(result)


def check_policy(sql: str) -> str | None:
    stripped = _strip_comments(sql).strip()
    if not stripped:
        return "Empty statement."

    head = stripped
    while head and (head[0] == "(" or head[0].isspace()):
        head = head[1:]
    first_token = head.split(None, 1)[0].lower() if head else ""
    if first_token not in ("select", "with"):
        return f"Statement type '{first_token}' is not allowed; only SELECT and WITH are permitted."

    body = stripped
    if body.endswith(";"):
        body = body[:-1]
    if ";" in body and not sqlite3.complete_statement(body + ";"):
        return "Multiple statements are not allowed."

    return None


def normalize_cell(value: Any) -> tuple[Any, bool]:
    if value is None:
        return None, False
    if isinstance(value, int):
        return value, False
    if isinstance(value, float):
        if math.isfinite(value):
            return value, False
        if math.isnan(value):
            return "NaN", False
        return ("Infinity" if value > 0 else "-Infinity"), False
    if isinstance(value, str):
        raw = value.encode("utf-8")
        if len(raw) <= MAX_CELL_BYTES:
            return value, False
        cut = raw[: MAX_CELL_BYTES - len(TRUNCATION_MARKER.encode("utf-8"))]
        return cut.decode("utf-8", errors="ignore") + TRUNCATION_MARKER, True
    if isinstance(value, bytes):
        preview = value[:BLOB_PREVIEW_BYTES].hex()
        text = f"<blob:{len(value)}:{preview}>"
        if len(value) > BLOB_PREVIEW_BYTES:
            return text[:-1] + "…>", True
        return text, False
    return str(value), False


def build_rows_envelope(columns: list[str], fetched: list[tuple]) -> dict:
    row_limited = len(fetched) > MAX_RETURN_ROWS
    candidates = fetched[:MAX_RETURN_ROWS]

    budget = MAX_ENVELOPE_BYTES - RESERVED_METADATA_BYTES - len(dumps(columns).encode("utf-8"))
    used = 0
    rows: list[list[Any]] = []
    cells_truncated = 0
    byte_limited = False

    for row in candidates:
        normalized_row = []
        for cell in row:
            value, was_truncated = normalize_cell(cell)
            normalized_row.append(value)
            if was_truncated:
                cells_truncated += 1
        size = len(dumps(normalized_row).encode("utf-8")) + 1
        if used + size > budget:
            byte_limited = True
            break
        used += size
        rows.append(normalized_row)

    truncated = row_limited or byte_limited
    if byte_limited:
        truncation_reason = "byte_limit"
    elif row_limited:
        truncation_reason = "row_limit"
    else:
        truncation_reason = None

    return {
        "columns": columns,
        "rows": rows,
        "row_count": len(rows),
        "truncated": truncated,
        "truncation_reason": truncation_reason,
        "cells_truncated": cells_truncated,
    }


mcp = MCPServer(
    name="mcp-shop-db",
    version="0.1.0",
    instructions="Read-only stdio MCP server over the shop.db SQLite database.",
)


@mcp.tool(structured_output=False)
def list_tables() -> str:
    """
    List every queryable table in the shop database with its row count and a
    short description of what it holds.

    Use this first, before writing any SQL, to discover what data exists.
    Takes no arguments. Internal SQLite tables and views are never listed.

    Returns JSON:
      {"ok": true,
       "tables": [{"name": "orders", "row_count": 750, "description": "..."}, ...]}
    Tables are ordered by name. On failure returns {"ok": false, "error": {...}}.
    """
    try:
        conn = open_connection(restricted=False)
    except FileNotFoundError:
        return err("db_unavailable", "Database file is not available.")

    try:
        names = [row[0] for row in conn.execute(LIST_TABLES_QUERY)]
        tables = []
        for name in names:
            count = conn.execute(f"SELECT COUNT(*) FROM {_quote_ident(name)}").fetchone()[0]
            tables.append(
                {
                    "name": name,
                    "row_count": count,
                    "description": TABLE_DESCRIPTIONS.get(name, NO_DESCRIPTION),
                }
            )
        return ok({"tables": tables})
    except sqlite3.Error as exc:
        return err("sql_error", str(exc)[:200])
    finally:
        conn.close()


@mcp.tool(structured_output=False)
def describe_table(
    table: Annotated[str, Field(description="Exact table name as returned by list_tables.")],
) -> str:
    """
    Describe one table: its columns with types and nullability, primary key,
    foreign keys, row count and original CREATE TABLE statement.

    Use this after list_tables to learn a table's exact column names before
    writing SQL. The `table` argument must be an exact name from list_tables;
    unknown names, views and internal SQLite tables are rejected.

    Returns JSON:
      {"ok": true, "table": "orders", "description": "...", "row_count": 750,
       "columns": [{"name": "id", "type": "INTEGER", "not_null": true,
                    "default": null, "primary_key": true}, ...],
       "foreign_keys": [{"column": "customer_id", "references_table": "customers",
                         "references_column": "id"}, ...],
       "ddl": "CREATE TABLE orders (...)"}
    On an unknown name returns {"ok": false, "error": {"code": "not_found",
    "message": "...", "known_tables": [...]}}.
    """
    try:
        conn = open_connection(restricted=False)
    except FileNotFoundError:
        return err("db_unavailable", "Database file is not available.")

    try:
        known = [row[0] for row in conn.execute(LIST_TABLES_QUERY)]
        if table not in known:
            return err("not_found", f"Unknown table '{table[:64]}'.", known_tables=sorted(known))

        columns = []
        for _cid, name, col_type, not_null, default, pk in conn.execute(
            'SELECT cid,name,type,"notnull",dflt_value,pk FROM pragma_table_info(?) ORDER BY cid',
            (table,),
        ):
            columns.append(
                {
                    "name": name,
                    "type": col_type,
                    "not_null": bool(not_null),
                    "default": default,
                    "primary_key": bool(pk),
                }
            )

        foreign_keys = []
        for from_col, ref_table, to_col in conn.execute(
            'SELECT "from","table","to" FROM pragma_foreign_key_list(?) ORDER BY id',
            (table,),
        ):
            foreign_keys.append(
                {
                    "column": from_col,
                    "references_table": ref_table,
                    "references_column": to_col,
                }
            )

        ddl_row = conn.execute(
            "SELECT sql FROM sqlite_master WHERE type='table' AND name=?", (table,)
        ).fetchone()
        ddl = ddl_row[0] if ddl_row else None

        row_count = conn.execute(f"SELECT COUNT(*) FROM {_quote_ident(table)}").fetchone()[0]

        return ok(
            {
                "table": table,
                "description": TABLE_DESCRIPTIONS.get(table, NO_DESCRIPTION),
                "row_count": row_count,
                "columns": columns,
                "foreign_keys": foreign_keys,
                "ddl": ddl,
            }
        )
    except sqlite3.Error as exc:
        return err("sql_error", str(exc)[:200])
    finally:
        conn.close()


@mcp.tool(structured_output=False)
def read_query(
    sql: Annotated[str, Field(description="One read-only SELECT or WITH ... SELECT statement.")],
) -> str:
    """
    Run one read-only SQL statement against the shop database and return the rows.

    Use this for every analytical question. Call list_tables and describe_table
    first if you do not already know the schema.

    Accepts exactly ONE statement, and only a SELECT or a WITH ... SELECT.
    Everything else is refused: INSERT, UPDATE, DELETE, DROP, ALTER, CREATE,
    REPLACE, PRAGMA, ATTACH, DETACH, VACUUM, EXPLAIN, transaction control and
    multiple statements separated by semicolons. The database is opened read-only,
    so no request can modify it.

    Limits: a query is cancelled after 2 seconds; at most 200 rows are returned;
    oversized text and binary values are truncated with a marker.

    Returns JSON:
      {"ok": true, "columns": ["name", "total"], "rows": [["Boots", 12], ...],
       "row_count": 2, "truncated": false, "truncation_reason": null,
       "cells_truncated": 0}
    `rows` is a list of positional arrays matching `columns`, so duplicate column
    names are preserved. NULL becomes null; binary values become
    "<blob:LENGTH:HEXPREFIX>". When `truncated` is true add LIMIT/ORDER BY or
    aggregate in SQL instead of paging.
    On failure returns {"ok": false, "error": {"code": "...", "message": "..."}}.
    """
    reason = check_policy(sql)
    if reason is not None:
        return err("policy_denied", reason[:200])

    try:
        conn = open_connection(restricted=True)
    except FileNotFoundError:
        return err("db_unavailable", "Database file is not available.")

    # CONTRACT: sqlite3.Warning is NOT a subclass of sqlite3.Error, so it needs its
    # own clause; SQLite reports authorizer denials and multi-statement input as
    # sqlite3.Error subclasses distinguished only by message text.
    try:
        cur = conn.execute(sql)
        columns = [d[0] for d in cur.description] if cur.description else []
        fetched = cur.fetchmany(MAX_FETCH_ROWS)
        return ok(build_rows_envelope(columns, fetched))
    except sqlite3.Warning as exc:
        return err("policy_denied", str(exc)[:200])
    except sqlite3.Error as exc:
        text = str(exc)
        low = text.lower()
        if "interrupted" in low:
            return err("timeout", "Query exceeded the 2s budget.")
        if "not authorized" in low or "only execute one statement" in low:
            return err("policy_denied", f"Denied by the read-only policy: {text[:160]}")
        return err("sql_error", text[:200])
    finally:
        conn.close()


def main() -> None:
    setup_logging()
    if not DB_PATH.is_file():
        log.error("Database not found at %s", DB_PATH)
        sys.exit(2)
    log.info("mcp-shop-db starting, database at %s", DB_PATH)
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
