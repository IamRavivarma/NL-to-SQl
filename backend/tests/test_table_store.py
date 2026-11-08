import pytest

from app.ingestion.loaders import Table
from app.sql.table_store import (
    MAX_ROWS,
    SqlError,
    TableStore,
    infer_type,
    sanitize_identifier,
    validate_select,
)


@pytest.fixture
def tables(tmp_path):
    return TableStore(str(tmp_path / "tables.db"))


def staff_table(rows=None):
    return Table(
        sheet=None,
        page=1,
        header=["Name", "Salary"],
        rows=rows if rows is not None else [["Alice", "52000"], ["Bob", "48000.5"]],
    )


@pytest.mark.parametrize(
    ("name", "expected"),
    [("Revenue (₹)", "revenue"), ("2024 Sales", "t_2024_sales"), ("Email Address", "email_address"), ("", "col")],
)
def test_sanitize_identifier(name, expected):
    assert sanitize_identifier(name, "col") == expected


@pytest.mark.parametrize(
    ("values", "expected"),
    [
        (["52000", "7", None], "INTEGER"),
        (["48000.5", "3"], "REAL"),
        ([52000, 48000.5], "REAL"),
        ([3, 4], "INTEGER"),
        (["12", "abc"], "TEXT"),
        (["007", "012"], "TEXT"),
        ([True, False], "TEXT"),
        ([None, None], "TEXT"),
    ],
)
def test_infer_type(values, expected):
    assert infer_type(values) == expected


def test_create_tables_records_catalog_and_typed_values(tables):
    names = tables.create_tables("doc1", "staff.csv", [staff_table()])
    assert names == ["staff"]
    [info] = tables.catalog()
    assert (info.table_name, info.document_id, info.filename, info.page, info.row_count) == (
        "staff",
        "doc1",
        "staff.csv",
        1,
        2,
    )
    assert info.columns == [
        {"name": "name", "original": "Name", "type": "TEXT"},
        {"name": "salary", "original": "Salary", "type": "REAL"},
    ]
    result = tables.run_select("SELECT name, salary FROM staff ORDER BY salary DESC")
    assert result.columns == ["name", "salary"]
    assert result.rows == [["Alice", 52000.0], ["Bob", 48000.5]]
    assert result.truncated is False


def test_duplicate_headers_get_unique_column_names(tables):
    table = Table(sheet=None, page=1, header=["Email Address", "Email Address", "Revenue (₹)"], rows=[["a", "b", "1"]])
    tables.create_tables("doc1", "form.csv", [table])
    assert [c["name"] for c in tables.catalog()[0].columns] == ["email_address", "email_address_2", "revenue"]


def test_mixed_type_column_is_text(tables):
    table = Table(sheet=None, page=1, header=["Code"], rows=[["12"], ["A7"]])
    tables.create_tables("doc1", "codes.csv", [table])
    assert tables.run_select("SELECT code FROM codes").rows == [["12"], ["A7"]]


def test_xlsx_table_name_includes_sheet_and_same_file_twice_is_deduplicated(tables):
    q1 = Table(sheet="Q1", page=1, header=["Region"], rows=[["North"]])
    assert tables.create_tables("doc1", "Sales 2024.xlsx", [q1]) == ["sales_2024_q1"]
    assert tables.create_tables("doc2", "Sales 2024.xlsx", [q1]) == ["sales_2024_q1_2"]


def test_drop_document_drops_only_its_tables(tables):
    tables.create_tables("doc1", "staff.csv", [staff_table()])
    tables.create_tables("doc2", "staff.csv", [staff_table()])
    assert tables.drop_document("doc1") == 1
    assert [info.table_name for info in tables.catalog()] == ["staff_2"]
    with pytest.raises(SqlError):
        tables.run_select("SELECT * FROM staff")


def test_sample_rows(tables):
    tables.create_tables("doc1", "staff.csv", [staff_table()])
    assert tables.sample_rows("staff", 1) == [("Alice", 52000.0)]


@pytest.mark.parametrize(
    "sql",
    ["DELETE FROM staff", "DROP TABLE staff", "SELECT 1; SELECT 2", "UPDATE staff SET name = 'x'", ""],
)
def test_non_select_sql_is_rejected(sql):
    with pytest.raises(SqlError):
        validate_select(sql)


def test_validate_select_accepts_with_and_trailing_semicolon():
    assert validate_select("  WITH t AS (SELECT 1) SELECT * FROM t; ") == "WITH t AS (SELECT 1) SELECT * FROM t"


def test_writes_cannot_run_even_inside_a_select_statement(tables):
    tables.create_tables("doc1", "staff.csv", [staff_table()])
    with pytest.raises(SqlError):
        tables.run_select("WITH x AS (SELECT 1) INSERT INTO staff VALUES ('Eve', 1)")
    assert tables.catalog()[0].row_count == 2
    assert len(tables.run_select("SELECT * FROM staff").rows) == 2


def test_results_are_capped(tables):
    tables.create_tables("doc1", "big.csv", [Table(sheet=None, page=1, header=["N"], rows=[[str(i)] for i in range(250)])])
    result = tables.run_select("SELECT n FROM big")
    assert len(result.rows) == MAX_ROWS == 200
    assert result.truncated is True


def test_sql_errors_carry_the_sqlite_message(tables):
    tables.create_tables("doc1", "staff.csv", [staff_table()])
    with pytest.raises(SqlError, match="no such column: age"):
        tables.run_select("SELECT age FROM staff")


def test_numbers_too_big_for_sqlite_integers_are_kept_as_text(tables):
    big = "12345678901234567890123"
    tables.create_tables("doc1", "ids.csv", [Table(sheet=None, page=1, header=["Id"], rows=[[big], ["7"]])])
    assert tables.catalog()[0].columns[0]["type"] == "TEXT"
    assert tables.run_select("SELECT id FROM ids").rows == [[big], ["7"]]


def test_catalog_can_be_limited_to_one_document(tables):
    tables.create_tables("doc1", "staff.csv", [staff_table()])
    tables.create_tables("doc2", "other.csv", [staff_table()])
    assert [t.table_name for t in tables.catalog("doc2")] == ["other"]
    assert len(tables.catalog()) == 2
