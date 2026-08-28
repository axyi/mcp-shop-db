import sqlite3

import pytest

import server

DENIED = [
    "INSERT INTO customers (first_name,last_name,email,created_at) VALUES ('a','b','c','d')",
    "UPDATE orders SET status='cancelled'",
    "DELETE FROM orders WHERE status='cancelled'",
    "DROP TABLE orders",
    "ALTER TABLE orders RENAME TO o2",
    "CREATE TABLE t (x INT)",
    "CREATE TEMP TABLE t (x INT)",
    "CREATE VIEW v AS SELECT 1",
    "CREATE INDEX ix ON orders(status)",
    "CREATE TRIGGER tr AFTER INSERT ON orders BEGIN SELECT 1; END",
    "CREATE VIRTUAL TABLE vt USING fts5(x)",
    "PRAGMA table_info(orders)",
    "PRAGMA query_only=OFF",
    "ATTACH DATABASE '/tmp/x.db' AS x",
    "DETACH DATABASE x",
    "BEGIN",
    "COMMIT",
    "ROLLBACK",
    "SAVEPOINT sp",
    "RELEASE sp",
    "VACUUM",
    "ANALYZE",
    "REINDEX",
    "EXPLAIN SELECT 1",
    "VALUES (1),(2)",
    "REPLACE INTO customers (id) VALUES (1)",
    "SELECT 1; SELECT 2",
    "SELECT 1; DROP TABLE orders",
    "-- comment\nDELETE FROM orders",
    "/* c */ UPDATE orders SET status='x'",
    "   ",
    "SELECT load_extension('/tmp/evil.so')",
    "SELECT * FROM pragma_table_info('orders')",
    "SELECT * FROM pragma_query_only",
]

ALLOWED = [
    "select 1 union select 2",
    "  WITH t AS (SELECT 1 x) SELECT * FROM t  ",
    "SELECT sqlite_version()",
    "SELECT * FROM sqlite_master",
    "SELECT COUNT(*) FROM customers WHERE phone LIKE '+79%'",
]


@pytest.mark.parametrize("sql", DENIED)
def test_denied_statements(call, sql):
    payload = call(server.read_query, sql)
    assert payload["ok"] is False, sql
    assert payload["error"]["code"] == "policy_denied", sql


def test_authorizer_not_lexical_gate_stops_functions(call):
    for sql in [
        "SELECT load_extension('/tmp/evil.so')",
        "SELECT * FROM pragma_table_info('orders')",
    ]:
        assert server.check_policy(sql) is None, sql
        payload = call(server.read_query, sql)
        assert payload["ok"] is False, sql
        assert "not authorized" in payload["error"]["message"].lower(), sql


@pytest.mark.parametrize("sql", ALLOWED)
def test_allowed_statements(call, sql):
    payload = call(server.read_query, sql)
    assert payload["ok"] is True, payload


def test_recursive_cte_and_aggregate_allowed(call):
    sql = (
        "WITH RECURSIVE seq(n) AS (SELECT 1 UNION ALL SELECT n+1 FROM seq WHERE n < 10) "
        "SELECT SUM(n) FROM seq"
    )
    payload = call(server.read_query, sql)
    assert payload["ok"] is True
    assert payload["rows"] == [[55]]


def test_connection_layer_independent_of_authorizer():
    conn = server.open_connection(restricted=False)
    try:
        row = conn.execute("PRAGMA query_only").fetchone()
        assert row[0] == 1
        with pytest.raises(sqlite3.OperationalError):
            conn.execute("DELETE FROM orders")
    finally:
        conn.close()


def test_no_side_files_created(call):
    db_dir = server.DB_PATH.parent
    before = set(p.name for p in db_dir.iterdir())
    payload = call(server.read_query, "SELECT COUNT(*) FROM customers")
    assert payload["ok"] is True
    after = set(p.name for p in db_dir.iterdir())
    assert before == after


def test_uri_quoting_for_special_characters(call, tmp_path):
    special_dir = tmp_path / "weird ?#& dir"
    special_dir.mkdir()
    db_file = special_dir / "shop.db"
    conn = sqlite3.connect(str(db_file))
    conn.execute("CREATE TABLE t (x INTEGER)")
    conn.execute("INSERT INTO t (x) VALUES (1)")
    conn.commit()
    conn.close()

    original = server.DB_PATH
    server.DB_PATH = db_file
    try:
        payload = call(server.read_query, "SELECT x FROM t")
        assert payload["ok"] is True
        assert payload["rows"] == [[1]]
    finally:
        server.DB_PATH = original


def test_missing_database_reports_db_unavailable(call, tmp_path):
    original = server.DB_PATH
    server.DB_PATH = tmp_path / "does-not-exist.db"
    try:
        payload = call(server.list_tables)
        assert payload["ok"] is False
        assert payload["error"]["code"] == "db_unavailable"
    finally:
        server.DB_PATH = original
