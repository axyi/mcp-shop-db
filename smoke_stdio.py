"""Standalone stdio smoke client: spawns server.py, drives it over real stdio."""

from __future__ import annotations

import asyncio
import json
import os
import sys
import tempfile
from pathlib import Path

from mcp import Client, StdioServerParameters
from mcp.client.stdio import stdio_client

HERE = Path(__file__).resolve().parent


def tool_payload(result) -> dict:
    """Decode the JSON envelope carried by the first text content block."""
    assert result.content, "tool returned no content blocks"
    block = result.content[0]
    assert block.type == "text", f"unexpected content block type: {block.type}"
    return json.loads(block.text)


async def run(mode: str) -> None:
    params = StdioServerParameters(
        command=sys.executable,
        args=[str(HERE / "server.py")],
        env={**os.environ},
        cwd=str(tempfile.gettempdir()),
    )
    with tempfile.TemporaryFile("w+", encoding="utf-8") as errlog:
        async with Client(stdio_client(params, errlog=errlog), mode=mode) as client:
            listed = await client.list_tools()
            names = {tool.name for tool in listed.tools}
            assert names == {"list_tables", "describe_table", "read_query"}, f"tools/list mismatch: {names}"
            for tool in listed.tools:
                assert tool.description, f"{tool.name} has no description"
                assert tool.input_schema, f"{tool.name} has no input schema"

            listed_tables = tool_payload(await client.call_tool("list_tables", {}))
            assert listed_tables["ok"] is True
            table_names = {t["name"] for t in listed_tables["tables"]}
            assert table_names == {"customers", "products", "orders", "order_items"}, table_names

            described = tool_payload(await client.call_tool("describe_table", {"table": "orders"}))
            assert described["ok"] is True
            assert described["row_count"] == 750, described["row_count"]

            counted = tool_payload(
                await client.call_tool("read_query", {"sql": "SELECT COUNT(*) AS n FROM customers"})
            )
            assert counted["ok"] is True
            assert counted["rows"] == [[150]], counted["rows"]

            denied = tool_payload(await client.call_tool("read_query", {"sql": "DELETE FROM orders"}))
            assert denied["ok"] is False
            assert denied["error"]["code"] == "policy_denied", denied

            hostile = tool_payload(
                await client.call_tool("describe_table", {"table": "customers; DROP TABLE x"})
            )
            assert hostile["ok"] is False
            assert hostile["error"]["code"] == "not_found", hostile
        errlog.seek(0)
        server_stderr = errlog.read()
    sys.stderr.write(server_stderr)
    print(f"SMOKE OK (mode={mode})")


async def main() -> None:
    await run("auto")
    await run("legacy")


if __name__ == "__main__":
    asyncio.run(main())
