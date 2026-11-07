import pytest

from app.sql.planner import describe_schema, parse_sql_plan
from app.sql.table_store import TableInfo

SALES = TableInfo(
    table_name="sales_q1",
    document_id="doc1",
    filename="sales.xlsx",
    page=1,
    columns=[
        {"name": "region", "original": "Region", "type": "TEXT"},
        {"name": "revenue", "original": "Revenue (₹)", "type": "INTEGER"},
    ],
    row_count=2,
)


def test_describe_schema_lists_tables_columns_and_samples():
    text = describe_schema([SALES], {"sales_q1": [("North", 120000), ("South", 95000)]})
    assert "sales_q1" in text
    assert "sales.xlsx p.1" in text
    assert "2 rows" in text
    assert "revenue INTEGER" in text
    assert "Revenue (₹)" in text
    assert "('North', 120000)" in text


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ('{"sql": "SELECT 1"}', "SELECT 1"),
        ('```json\n{"sql": "SELECT region FROM sales_q1"}\n```', "SELECT region FROM sales_q1"),
        ('Here is the query:\n{"sql": "SELECT 2"} hope it helps', "SELECT 2"),
        ('{"sql": "  SELECT 3  "}', "SELECT 3"),
        ('{"sql": null}', None),
        ('{"sql": ""}', None),
        ("I don't know", None),
        ('{"sql": "SELECT 1"', None),
        ('{"query": "SELECT 1"}', None),
    ],
)
def test_parse_sql_plan(text, expected):
    assert parse_sql_plan(text) == expected
