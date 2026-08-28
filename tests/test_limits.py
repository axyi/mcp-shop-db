import time

import server


def test_row_limit(call):
    sql = (
        "WITH RECURSIVE s(n) AS (SELECT 1 UNION ALL SELECT n+1 FROM s WHERE n<1000) "
        "SELECT n FROM s"
    )
    payload = call(server.read_query, sql)
    assert payload["ok"] is True
    assert payload["row_count"] == 200
    assert payload["truncated"] is True
    assert payload["truncation_reason"] == "row_limit"


def test_byte_limit(call):
    sql = "SELECT hex(zeroblob(3000)) FROM order_items LIMIT 200"
    raw = server.read_query(sql)
    payload = call(server.read_query, sql)
    assert payload["ok"] is True
    assert payload["truncated"] is True
    assert payload["truncation_reason"] == "byte_limit"
    assert payload["row_count"] < 200
    assert len(raw.encode("utf-8")) <= server.MAX_ENVELOPE_BYTES


def test_oversized_text_cell_truncated(call):
    payload = call(server.read_query, "SELECT hex(zeroblob(6000))")
    assert payload["ok"] is True
    cell = payload["rows"][0][0]
    assert cell.endswith("…[truncated]")
    assert len(cell.encode("utf-8")) <= server.MAX_CELL_BYTES
    assert payload["cells_truncated"] == 1


def test_oversized_blob_cell_truncated(call):
    payload = call(server.read_query, "SELECT zeroblob(5000)")
    assert payload["ok"] is True
    cell = payload["rows"][0][0]
    assert cell.startswith("<blob:5000:")
    assert cell.endswith("…>")
    assert payload["cells_truncated"] == 1


def test_query_budget_timeout(call):
    sql = (
        "WITH RECURSIVE s(n) AS (SELECT 1 UNION ALL SELECT n+1 FROM s WHERE n<200000000) "
        "SELECT COUNT(*) FROM s"
    )
    start = time.monotonic()
    payload = call(server.read_query, sql)
    elapsed = time.monotonic() - start
    assert payload["ok"] is False
    assert payload["error"]["code"] == "timeout"
    assert elapsed < 10.0
