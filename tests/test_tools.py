import server


def test_list_tables_happy_path(call):
    payload = call(server.list_tables)
    assert payload["ok"] is True
    names = {t["name"] for t in payload["tables"]}
    assert names == {"customers", "products", "orders", "order_items"}
    assert "sqlite_sequence" not in names
    row_counts = {t["name"]: t["row_count"] for t in payload["tables"]}
    assert row_counts == {
        "customers": 150,
        "products": 50,
        "orders": 750,
        "order_items": 1900,
    }
    assert all(t["description"] for t in payload["tables"])


def test_describe_table_order_items(call):
    payload = call(server.describe_table, "order_items")
    assert payload["ok"] is True
    assert [c["name"] for c in payload["columns"]] == [
        "id",
        "order_id",
        "product_id",
        "quantity",
        "unit_price",
    ]
    assert payload["columns"][0]["primary_key"] is True
    fks = {(fk["column"], fk["references_table"]) for fk in payload["foreign_keys"]}
    assert fks == {("order_id", "orders"), ("product_id", "products")}
    assert payload["row_count"] == 1900
    assert payload["ddl"].startswith("CREATE TABLE order_items")


def test_describe_table_customers_nullability(call):
    payload = call(server.describe_table, "customers")
    columns = {c["name"]: c for c in payload["columns"]}
    assert columns["phone"]["not_null"] is False
    assert columns["email"]["not_null"] is True


def test_read_query_count(call):
    payload = call(server.read_query, "SELECT COUNT(*) AS n FROM customers")
    assert payload["columns"] == ["n"]
    assert payload["rows"] == [[150]]


def test_read_query_duplicate_columns_empty_result(call):
    payload = call(server.read_query, "SELECT id, id FROM customers WHERE 1=0")
    assert payload["columns"] == ["id", "id"]
    assert payload["rows"] == []
    assert payload["row_count"] == 0
    assert payload["truncated"] is False


def test_read_query_null_blob_float_text(call):
    payload = call(server.read_query, "SELECT NULL, x'deadbeef', 1.5, 'ok'")
    assert payload["rows"][0] == [None, "<blob:4:deadbeef>", 1.5, "ok"]


def test_read_query_non_finite_floats(call):
    payload = call(server.read_query, "SELECT 1e400, -1e400")
    assert payload["rows"] == [["Infinity", "-Infinity"]]


def test_read_query_unknown_table(call):
    payload = call(server.read_query, "SELECT * FROM nosuchtable")
    assert payload["ok"] is False
    assert payload["error"]["code"] == "sql_error"


HOSTILE_NAMES = [
    "sqlite_sequence",
    "nope",
    'orders"; DROP TABLE orders; --',
    "orders --",
    "",
    "ORDERS",
]


def test_describe_table_hostile_names(call):
    for name in HOSTILE_NAMES:
        payload = call(server.describe_table, name)
        assert payload["ok"] is False, name
        assert payload["error"]["code"] == "not_found", name
        known = set(payload["error"]["known_tables"])
        assert {"customers", "products", "orders", "order_items"} <= known, name


def test_hostile_name_does_not_execute(call):
    for name in HOSTILE_NAMES:
        call(server.describe_table, name)
    payload = call(server.list_tables)
    row_counts = {t["name"]: t["row_count"] for t in payload["tables"]}
    assert row_counts["orders"] == 750


def test_tools_never_write_stdout(call, capsys):
    call(server.list_tables)
    call(server.describe_table, "orders")
    call(server.read_query, "SELECT 1")
    captured = capsys.readouterr()
    assert captured.out == ""
