import csv
from dataclasses import dataclass
from datetime import datetime
from io import BytesIO, StringIO
from pathlib import PurePath

import docx2txt
import openpyxl
from pypdf import PdfReader

MAX_FILE_BYTES = 20 * 1024 * 1024
SUPPORTED_TYPES = ("pdf", "txt", "docx", "csv", "xlsx")
NO_ROWS_MESSAGE = "No data rows found in this spreadsheet."


class DocumentLoadError(ValueError):
    """Raised with a message that can be shown to the user as-is."""


@dataclass(frozen=True)
class Page:
    text: str
    page_number: int  # 1-based


@dataclass(frozen=True)
class Table:
    sheet: str | None  # Excel sheet name; None for CSV
    page: int  # sheet position (1-based); 1 for CSV
    header: list[str]
    rows: list[list]  # raw cell values (str for CSV, typed for XLSX); None for empty cells


def detect_file_type(filename: str) -> str:
    file_type = PurePath(filename or "").suffix.lower().lstrip(".")
    if file_type not in SUPPORTED_TYPES:
        raise DocumentLoadError("Unsupported file type. Upload a PDF, TXT, DOCX, CSV or Excel (.xlsx) file.")
    return file_type


def load_pages(filename: str, content: bytes) -> tuple[str, list[Page], int]:
    """Return the file type, the pages that contain text, and the total page count (blank pages included)."""
    file_type = detect_file_type(filename)
    if not content:
        raise DocumentLoadError("The file is empty.")
    if len(content) > MAX_FILE_BYTES:
        raise DocumentLoadError("The file is larger than 20 MB.")

    if file_type == "pdf":
        pages = _load_pdf(content)
    elif file_type == "docx":
        pages = [Page(text=_load_docx(content), page_number=1)]
    elif file_type == "csv":
        pages = [Page(text=_load_csv(content), page_number=1)]
    elif file_type == "xlsx":
        pages = _load_xlsx(content)
    else:
        pages = [Page(text=_decode_text(content), page_number=1)]

    page_count = len(pages)
    pages = [page for page in pages if page.text.strip()]
    if not pages:
        if file_type in ("csv", "xlsx"):
            raise DocumentLoadError(NO_ROWS_MESSAGE)
        raise DocumentLoadError("No readable text found — scanned PDFs aren't supported.")
    return file_type, pages, page_count


def _load_pdf(content: bytes) -> list[Page]:
    try:
        reader = PdfReader(BytesIO(content))
        if reader.is_encrypted:
            raise DocumentLoadError("Password-protected PDFs aren't supported.")
        return [Page(text=page.extract_text() or "", page_number=i + 1) for i, page in enumerate(reader.pages)]
    except DocumentLoadError:
        raise
    except Exception as exc:
        raise DocumentLoadError("Could not read this PDF file.") from exc


def _load_docx(content: bytes) -> str:
    try:
        return docx2txt.process(BytesIO(content)) or ""
    except Exception as exc:
        raise DocumentLoadError("Could not read this DOCX file.") from exc


def load_tables(filename: str, content: bytes) -> list[Table]:
    """Parse a CSV or XLSX file into tables with at least one data row; other file types have none."""
    file_type = detect_file_type(filename)
    if file_type == "csv":
        tables = [_parse_table(_read_csv_rows(content), sheet=None, page=1)]
    elif file_type == "xlsx":
        tables = _read_xlsx_tables(content)
    else:
        return []
    return [table for table in tables if table.rows]


def _load_csv(content: bytes) -> str:
    return "\n".join(_table_lines(_parse_table(_read_csv_rows(content), sheet=None, page=1)))


def _load_xlsx(content: bytes) -> list[Page]:
    pages = []
    for table in _read_xlsx_tables(content):
        lines = _table_lines(table)
        text = "\n".join([f"Sheet: {table.sheet}", *lines]) if lines else ""
        pages.append(Page(text=text, page_number=table.page))
    return pages


def _read_csv_rows(content: bytes) -> list[list]:
    text = _decode_text(content)
    try:
        dialect = csv.Sniffer().sniff(text[:4096], delimiters=",;\t|")
    except csv.Error:
        dialect = csv.excel
    try:
        return list(csv.reader(StringIO(text), dialect))
    except csv.Error as exc:
        raise DocumentLoadError("Could not read this CSV file.") from exc


def _read_xlsx_tables(content: bytes) -> list[Table]:
    """One table per worksheet, empty ones included, so page numbers match sheet positions."""
    try:
        workbook = openpyxl.load_workbook(BytesIO(content), read_only=True, data_only=True)
    except Exception as exc:
        raise DocumentLoadError("Could not read this Excel file.") from exc
    try:
        return [
            _parse_table(sheet.iter_rows(values_only=True), sheet=sheet.title, page=number)
            for number, sheet in enumerate(workbook.worksheets, start=1)
        ]
    finally:
        workbook.close()


def _parse_table(rows, *, sheet: str | None, page: int) -> Table:
    """The first non-empty row is the header; empty rows are skipped and empty cells become None.

    Blank header cells are named "Column N"; columns with a blank header and no values are dropped.
    """
    header: list[str] | None = None
    data: list[list] = []
    for row in rows:
        values = [None if cell_text(value) == "" else value for value in row]
        if not any(value is not None for value in values):
            continue
        if header is None:
            header = [cell_text(value) for value in values]
        else:
            data.append(values)
    if header is None:
        return Table(sheet=sheet, page=page, header=[], rows=[])

    width = max([len(header), *(len(row) for row in data)])
    header = header + [""] * (width - len(header))
    data = [row + [None] * (width - len(row)) for row in data]
    keep = [i for i in range(width) if header[i] or any(row[i] is not None for row in data)]
    return Table(
        sheet=sheet,
        page=page,
        header=[header[i] or f"Column {i + 1}" for i in keep],
        rows=[[row[i] for i in keep] for row in data],
    )


def _table_lines(table: Table) -> list[str]:
    """Turn rows into "Column: value | Column: value" lines, so every chunk keeps the column names."""
    return [
        " | ".join(f"{name}: {cell_text(value)}" for name, value in zip(table.header, row) if value is not None)
        for row in table.rows
    ]


def cell_text(value) -> str:
    if value is None:
        return ""
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    if isinstance(value, datetime):
        return value.date().isoformat() if value.time() == datetime.min.time() else value.isoformat(sep=" ")
    return str(value).strip()


def _decode_text(content: bytes) -> str:
    if content.startswith((b"\xff\xfe", b"\xfe\xff")):
        # UTF-16 with a byte-order mark (Notepad's "Unicode" option); the BOM picks the byte order.
        return content.decode("utf-16")
    try:
        return content.decode("utf-8-sig")
    except UnicodeDecodeError:
        # Windows-1252 is the usual non-UTF-8 encoding for text files saved on Windows.
        return content.decode("cp1252", errors="replace")
