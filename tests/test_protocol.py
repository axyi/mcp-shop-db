import asyncio
import json

from mcp import Client

import server


def test_protocol_boundary():
    async def run():
        async with Client(server.mcp) as client:
            listed = await client.list_tools()
            names = {tool.name for tool in listed.tools}
            assert names == {"list_tables", "describe_table", "read_query"}

            by_name = {tool.name: tool for tool in listed.tools}
            for tool in by_name.values():
                assert tool.description
                assert len(tool.description) > 100
                assert tool.input_schema

            describe_schema = by_name["describe_table"].input_schema
            assert describe_schema["required"] == ["table"]
            assert describe_schema["properties"]["table"].get("description")

            read_query_schema = by_name["read_query"].input_schema
            assert read_query_schema["required"] == ["sql"]
            assert read_query_schema["properties"]["sql"].get("description")

            result = await client.call_tool("read_query", {"sql": "SELECT 1 AS one"})
            assert result.is_error is False
            payload = json.loads(result.content[0].text)
            assert payload["rows"] == [[1]]

            denied = await client.call_tool("read_query", {"sql": "DROP TABLE orders"})
            assert denied.is_error is False
            denied_payload = json.loads(denied.content[0].text)
            assert denied_payload["ok"] is False
            assert denied_payload["error"]["code"] == "policy_denied"

    asyncio.run(run())
