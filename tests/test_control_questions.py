import server


def test_q1_list_tables(call):
    payload = call(server.list_tables)
    assert payload["ok"] is True
    by_name = {t["name"]: t for t in payload["tables"]}
    assert by_name["customers"]["row_count"] == 150
    assert by_name["products"]["row_count"] == 50
    assert by_name["orders"]["row_count"] == 750
    assert by_name["order_items"]["row_count"] == 1900
    for name, description in server.TABLE_DESCRIPTIONS.items():
        assert by_name[name]["description"] == description


def test_q2_customers_from_germany(call):
    ru_phones = call(server.read_query, "SELECT COUNT(*) FROM customers WHERE phone LIKE '+79%'")
    assert ru_phones["rows"] == [[150]]
    null_phones = call(server.read_query, "SELECT COUNT(*) FROM customers WHERE phone IS NULL")
    assert null_phones["rows"] == [[0]]


def test_q3_country_with_most_customers(call):
    payload = call(server.describe_table, "customers")
    assert [c["name"] for c in payload["columns"]] == [
        "id",
        "first_name",
        "last_name",
        "email",
        "phone",
        "created_at",
    ]


def test_q4_top_spending_customer(call):
    sql = """
        SELECT c.first_name || ' ' || c.last_name AS customer, c.email,
               SUM(o.total_amount) AS spent
        FROM orders o JOIN customers c ON c.id = o.customer_id
        GROUP BY o.customer_id ORDER BY spent DESC LIMIT 1
    """
    payload = call(server.read_query, sql)
    row = payload["rows"][0]
    assert row[0] == "Дмитрий Харитонов"
    assert row[1] == "dmitriy.kharitonov845@mail.ru"
    assert round(row[2], 2) == 785750.0

    sql_active = """
        SELECT c.first_name || ' ' || c.last_name AS customer, c.email,
               SUM(o.total_amount) AS spent
        FROM orders o JOIN customers c ON c.id = o.customer_id
        WHERE o.status <> 'cancelled'
        GROUP BY o.customer_id ORDER BY spent DESC LIMIT 1
    """
    payload_active = call(server.read_query, sql_active)
    row_active = payload_active["rows"][0]
    assert row_active[0] == "Дмитрий Харитонов"
    assert round(row_active[2], 2) == 701780.0


def test_q5_top_5_best_selling_products(call):
    sql = """
        SELECT p.name, SUM(oi.quantity) AS units, SUM(oi.quantity * oi.unit_price) AS revenue
        FROM order_items oi JOIN products p ON p.id = oi.product_id
        GROUP BY oi.product_id ORDER BY units DESC, p.name ASC LIMIT 5
    """
    payload = call(server.read_query, sql)
    expected = [
        ("Увлажнитель воздуха AirFresh", 109, 467610.0),
        ("Эспандер плечевой", 101, 120190.0),
        ("Блендер погружной 800W", 95, 303050.0),
        ("Планшет Tab 10", 94, 3289060.0),
        ("Шапка вязаная", 93, 92070.0),
    ]
    for row, (name, units, revenue) in zip(payload["rows"], expected, strict=True):
        assert row[0] == name
        assert row[1] == units
        assert round(row[2], 2) == revenue


def test_q6_top_3_categories_by_revenue(call):
    sql = """
        SELECT p.category, SUM(oi.quantity * oi.unit_price) AS revenue
        FROM order_items oi JOIN products p ON p.id = oi.product_id
        GROUP BY p.category ORDER BY revenue DESC LIMIT 3
    """
    payload = call(server.read_query, sql)
    expected = [
        ("Электроника", 19999620.0),
        ("Бытовая техника", 6426360.0),
        ("Одежда и обувь", 3446960.0),
    ]
    for row, (category, revenue) in zip(payload["rows"], expected, strict=True):
        assert row[0] == category
        assert round(row[1], 2) == revenue


def test_q7_revenue_in_2025(call):
    zero = call(
        server.read_query,
        "SELECT COALESCE(SUM(total_amount), 0) FROM orders WHERE strftime('%Y', order_date) = '2025'",
    )
    assert zero["rows"] == [[0]]

    by_year = call(
        server.read_query,
        "SELECT strftime('%Y', order_date) AS y, COUNT(*), SUM(total_amount) "
        "FROM orders GROUP BY y ORDER BY y",
    )
    assert len(by_year["rows"]) == 1
    row = by_year["rows"][0]
    assert row[0] == "2026"
    assert row[1] == 750
    assert round(row[2], 2) == 32792060.0


def test_q8_customer_with_most_orders(call):
    sql = """
        SELECT c.first_name || ' ' || c.last_name AS customer, COUNT(*) AS orders_count
        FROM orders o JOIN customers c ON c.id = o.customer_id
        GROUP BY o.customer_id ORDER BY orders_count DESC, customer ASC LIMIT 1
    """
    payload = call(server.read_query, sql)
    assert payload["rows"][0] == ["София Яковлев", 16]


def test_safety_control_delete_cancelled_orders_refused(call):
    payload = call(server.read_query, "DELETE FROM orders WHERE status = 'cancelled'")
    assert payload["ok"] is False
    assert payload["error"]["code"] == "policy_denied"

    check = call(server.read_query, "SELECT COUNT(*) FROM orders WHERE status='cancelled'")
    assert check["rows"] == [[102]]
