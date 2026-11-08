import json
import re
import sqlite3
import time
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path, PurePath

from app.core.config import settings
from app.ingestion.loaders import Table, cell_text

MAX_ROWS = 200
TIME_LIMIT_SECONDS = 5
CATALOG = "_catalog"

_INTEGER = re.compile(r"[+-]?\d+")
_NUMBER = re.compile(r"[+-]?(\d+\.?\d*|\.\d+)([eE][+-]?\d+)?")
_SELECT_START = re.compile(r"(select|with)\b", re.IGNORECASE)


class SqlError(Exception):
    """A query that was rejected or failed; the message can be shown to the user."""


@dataclass
class TableInfo:
    table_name: str
    document_id: str
    filename: str
    page: int
    columns: list[dict]  # {"name", "original", "type"}
    row_count: int


@dataclass
class QueryResult:
    columns: list[str]
    rows: list[list]
    truncated: bool


def sanitize_identifier(name: str, fallback: str) -> str:
    cleaned = re.sub(r"[^a-z0-9]+", "_", str(name).lower()).strip("_")
    if not cleaned:
        return fallback
    return f"t_{cleaned}" if cleaned[0].isdigit() else cleaned


def _fits_sqlite_integer(value: int) -> bool:
    return -(2**63) <= value < 2**63


def _is_int_text(value: str) -> bool:
    # Leading zeros ("007", phone numbers, codes) are identifiers, not numbers.
    digits = value.lstrip("+-")
    return (
        bool(_INTEGER.fullmatch(value))
        and not (len(digits) > 1 and digits[0] == "0")
        and _fits_sqlite_integer(int(value))
    )


def infer_type(values: list) -> str:
    present = [value for value in values if value is not None]
    if not present or any(isinstance(value, bool) for value in present):
        return "TEXT"
    if all(
        (isinstance(value, int) and _fits_sqlite_integer(value))
        or (isinstance(value, str) and _is_int_text(value.strip()))
        for value in present
    ):
        return "INTEGER"
    if all(isinstance(value, (int, float)) or (isinstance(value, str) and _is_real_text(value.strip())) for value in present):
        return "REAL"
    return "TEXT"


def _is_real_text(value: str) -> bool:
    # Whole-number text that isn't a safe integer ("007", 20-digit ids) is an identifier: keep every digit as text.
    if _INTEGER.fullmatch(value):
        return _is_int_text(value)
    return bool(_NUMBER.fullmatch(value))


def _convert(value, column_type: str):
    if value is None:
        return None
    if column_type == "INTEGER":
        return int(value.strip()) if isinstance(value, str) else int(value)
    if column_type == "REAL":
        return float(value.strip()) if isinstance(value, str) else float(value)
    return cell_text(value)  # dates become ISO text


def validate_select(sql: str) -> str:
    statement = sql.strip().rstrip(";").strip()
    if not statement or ";" in statement:
        raise SqlError("Only a single SELECT statement is allowed.")
    if not _SELECT_START.match(statement):
        raise SqlError("Only SELECT queries are allowed.")
    return statement


def _unique(name: str, taken: set[str]) -> str:
    candidate, n = name, 2
    while candidate in taken:
        candidate, n = f"{name}_{n}", n + 1
    taken.add(candidate)
    return candidate


class TableStore:
    """Spreadsheet rows as SQLite tables. Every call opens its own connection, so it is thread-safe."""

    def __init__(self, path: str):
        self._path = Path(path).resolve()
        self._path.parent.mkdir(parents=True, exist_ok=True)
        with self._write() as conn:
            conn.execute(
                f'CREATE TABLE IF NOT EXISTS "{CATALOG}" (table_name TEXT PRIMARY KEY, document_id TEXT NOT NULL, '
                "filename TEXT NOT NULL, page INTEGER NOT NULL, columns TEXT NOT NULL, row_count INTEGER NOT NULL)"
            )

    def _write(self) -> sqlite3.Connection:
        return sqlite3.connect(self._path, isolation_level=None)

    def _read(self) -> sqlite3.Connection:
        conn = sqlite3.connect(f"{self._path.as_uri()}?mode=ro", uri=True)
        conn.execute("PRAGMA query_only = ON")
        return conn

    def create_tables(self, document_id: str, filename: str, tables: list[Table]) -> list[str]:
        conn = self._write()
        try:
            conn.execute("BEGIN")
            taken = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
            stem = sanitize_identifier(PurePath(filename).stem, "table")
            names = []
            for table in tables:
                base = stem if table.sheet is None else f"{stem}_{sanitize_identifier(table.sheet, 'sheet')}"
                table_name = _unique(base, taken)
                used: set[str] = set()
                columns = []
                for i, original in enumerate(table.header):
                    values = [row[i] for row in table.rows]
                    columns.append(
                        {
                            "name": _unique(sanitize_identifier(original, f"column_{i + 1}"), used),
                            "original": original,
                            "type": infer_type(values),
                        }
                    )
                column_sql = ", ".join(f'"{c["name"]}" {c["type"]}' for c in columns)
                conn.execute(f'CREATE TABLE "{table_name}" ({column_sql})')
                placeholders = ", ".join("?" for _ in columns)
                conn.executemany(
                    f'INSERT INTO "{table_name}" VALUES ({placeholders})',
                    [[_convert(value, c["type"]) for value, c in zip(row, columns)] for row in table.rows],
                )
                conn.execute(
                    f'INSERT INTO "{CATALOG}" VALUES (?, ?, ?, ?, ?, ?)',
                    (table_name, document_id, filename, table.page, json.dumps(columns), len(table.rows)),
                )
                names.append(table_name)
            conn.execute("COMMIT")
            return names
        except Exception:
            conn.execute("ROLLBACK")
            raise
        finally:
            conn.close()

    def drop_document(self, document_id: str) -> int:
        conn = self._write()
        try:
            conn.execute("BEGIN")
            names = [
                row[0]
                for row in conn.execute(f'SELECT table_name FROM "{CATALOG}" WHERE document_id = ?', (document_id,))
            ]
            for name in names:
                conn.execute(f'DROP TABLE IF EXISTS "{name}"')
            conn.execute(f'DELETE FROM "{CATALOG}" WHERE document_id = ?', (document_id,))
            conn.execute("COMMIT")
            return len(names)
        except Exception:
            conn.execute("ROLLBACK")
            raise
        finally:
            conn.close()

    def catalog(self) -> list[TableInfo]:
        with self._read() as conn:
            rows = conn.execute(
                f'SELECT table_name, document_id, filename, page, columns, row_count FROM "{CATALOG}" ORDER BY rowid'
            ).fetchall()
        return [TableInfo(name, doc, filename, page, json.loads(cols), count) for name, doc, filename, page, cols, count in rows]

    def sample_rows(self, table_name: str, n: int = 3) -> list[tuple]:
        with self._read() as conn:
            return conn.execute(f'SELECT * FROM "{table_name}" LIMIT ?', (n,)).fetchall()

    def run_select(self, sql: str) -> QueryResult:
        statement = validate_select(sql)
        conn = self._read()
        deadline = time.monotonic() + TIME_LIMIT_SECONDS
        conn.set_progress_handler(lambda: 1 if time.monotonic() > deadline else 0, 10_000)
        try:
            cursor = conn.execute(statement)
            rows = cursor.fetchmany(MAX_ROWS + 1)
            columns = [d[0] for d in cursor.description or []]
        except sqlite3.OperationalError as exc:
            if str(exc) == "interrupted":
                raise SqlError(f"The query took longer than {TIME_LIMIT_SECONDS} seconds.") from exc
            raise SqlError(str(exc)) from exc
        except sqlite3.Error as exc:
            raise SqlError(str(exc)) from exc
        finally:
            conn.close()
        return QueryResult(columns=columns, rows=[list(r) for r in rows[:MAX_ROWS]], truncated=len(rows) > MAX_ROWS)


@lru_cache
def get_table_store() -> TableStore:
    return TableStore(settings.sqlite_path)
