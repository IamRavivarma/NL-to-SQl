from datetime import datetime

import pytest

from app.ingestion.loaders import MAX_FILE_BYTES, DocumentLoadError, Page, Table, load_pages, load_tables
from tests.files import make_docx, make_pdf, make_xlsx


def test_pdf_pages_keep_page_numbers_and_skip_blank_pages():
    file_type, pages, _ = load_pages("guide.pdf", make_pdf(["Intro to refunds", "", "Shipping takes 5 days"]))
    assert file_type == "pdf"
    assert [p.page_number for p in pages] == [1, 3]
    assert "refunds" in pages[0].text
    assert "Shipping" in pages[1].text


def test_page_count_includes_trailing_blank_pages():
    _, pages, page_count = load_pages("guide.pdf", make_pdf(["Only page with text", "", ""]))
    assert len(pages) == 1
    assert page_count == 3


def test_uppercase_extension_is_accepted():
    file_type, _, _ = load_pages("REPORT.PDF", make_pdf(["Quarterly numbers"]))
    assert file_type == "pdf"


def test_docx_is_one_page():
    file_type, pages, _ = load_pages("notes.docx", make_docx(["First paragraph.", "Second paragraph."]))
    assert file_type == "docx"
    assert len(pages) == 1 and pages[0].page_number == 1
    assert "Second paragraph." in pages[0].text


def test_txt_utf8_with_bom():
    _, pages, _ = load_pages("a.txt", "\ufeffCafé menu".encode("utf-8"))
    assert pages == [Page(text="Café menu", page_number=1)]


def test_txt_windows_1252_falls_back_without_crashing():
    _, pages, _ = load_pages("a.txt", "Café – menu".encode("cp1252"))
    assert "Caf" in pages[0].text and "menu" in pages[0].text


@pytest.mark.parametrize("encoding", ["utf-16", "utf-16-be"])
def test_txt_utf16_with_bom_is_decoded(encoding):
    # Notepad's "Unicode" option saves UTF-16 with a byte-order mark.
    content = "Refunds take ten days".encode(encoding)
    if encoding == "utf-16-be":
        content = b"\xfe\xff" + content
    _, pages, _ = load_pages("a.txt", content)
    assert pages == [Page(text="Refunds take ten days", page_number=1)]


def test_csv_rows_carry_their_column_names():
    content = b"Name,Department,Salary\nAlice,Sales,52000\nBob,,48000\n"
    file_type, pages, page_count = load_pages("staff.csv", content)
    assert file_type == "csv"
    assert page_count == 1
    assert pages == [
        Page(text="Name: Alice | Department: Sales | Salary: 52000\nName: Bob | Salary: 48000", page_number=1)
    ]


def test_csv_semicolon_delimiter_is_detected():
    # Excel in many European locales saves CSV with semicolons.
    _, pages, _ = load_pages("staff.csv", "Name;City\nZoë;Paris\n".encode("cp1252"))
    assert pages[0].text == "Name: Zoë | City: Paris"


def test_csv_blank_header_gets_a_column_number():
    _, pages, _ = load_pages("a.csv", b"Name,\nAlice,VIP\n")
    assert pages[0].text == "Name: Alice | Column 2: VIP"


def test_csv_with_only_a_header_is_rejected():
    with pytest.raises(DocumentLoadError, match="No data rows found"):
        load_pages("a.csv", b"Name,City\n")


def test_xlsx_sheets_are_pages():
    content = make_xlsx(
        {
            "Staff": [["Name", "Salary", "Joined"], ["Alice", 52000.0, datetime(2024, 3, 1)], ["Bob", 48000.5, None]],
            "Empty": [],
            "Offices": [["City"], ["Paris"]],
        }
    )
    file_type, pages, page_count = load_pages("company.xlsx", content)
    assert file_type == "xlsx"
    assert page_count == 3
    assert pages == [
        Page(text="Sheet: Staff\nName: Alice | Salary: 52000 | Joined: 2024-03-01\nName: Bob | Salary: 48000.5", page_number=1),
        Page(text="Sheet: Offices\nCity: Paris", page_number=3),
    ]


def test_xlsx_header_is_the_first_non_empty_row():
    content = make_xlsx({"Report": [[None, None], ["Item", "Qty"], ["Pens", 3]]})
    _, pages, _ = load_pages("report.xlsx", content)
    assert pages[0].text == "Sheet: Report\nItem: Pens | Qty: 3"


def test_xlsx_without_data_rows_is_rejected():
    with pytest.raises(DocumentLoadError, match="No data rows found"):
        load_pages("empty.xlsx", make_xlsx({"Sheet1": [["Only", "Headers"]]}))


def test_corrupt_xlsx_is_rejected():
    with pytest.raises(DocumentLoadError, match="Could not read"):
        load_pages("broken.xlsx", b"not a zip file")


def test_load_tables_csv():
    assert load_tables("staff.csv", b"Name,Salary\nAlice,52000\n") == [
        Table(sheet=None, page=1, header=["Name", "Salary"], rows=[["Alice", "52000"]])
    ]


def test_load_tables_xlsx_skips_empty_sheets():
    content = make_xlsx(
        {
            "Staff": [["Name", None], ["Alice", "VIP"]],
            "Empty": [],
            "Offices": [["City"], ["Paris"]],
        }
    )
    tables = load_tables("company.xlsx", content)
    assert [(t.sheet, t.page) for t in tables] == [("Staff", 1), ("Offices", 3)]
    assert tables[0].header == ["Name", "Column 2"]
    assert tables[0].rows == [["Alice", "VIP"]]


def test_load_tables_header_only_sheet_is_skipped():
    content = make_xlsx({"Headers": [["Only", "Headers"]], "Data": [["City"], ["Paris"]]})
    assert [t.sheet for t in load_tables("a.xlsx", content)] == ["Data"]


def test_load_tables_pdf_is_empty():
    assert load_tables("a.pdf", make_pdf(["Some text"])) == []


@pytest.mark.parametrize("filename", ["old.xls", "notes", "image.png"])
def test_unsupported_types_are_rejected(filename):
    with pytest.raises(DocumentLoadError, match="Unsupported file type"):
        load_pages(filename, b"hello")


def test_empty_file_is_rejected():
    with pytest.raises(DocumentLoadError, match="empty"):
        load_pages("a.txt", b"")


def test_too_large_file_is_rejected():
    with pytest.raises(DocumentLoadError, match="20 MB"):
        load_pages("a.txt", b"x" * (MAX_FILE_BYTES + 1))


def test_pdf_without_text_is_rejected():
    with pytest.raises(DocumentLoadError, match="No readable text found"):
        load_pages("scan.pdf", make_pdf(["", ""]))


def test_corrupt_pdf_is_rejected():
    with pytest.raises(DocumentLoadError, match="Could not read"):
        load_pages("broken.pdf", b"%PDF-1.4 not really a pdf")


def test_corrupt_docx_is_rejected():
    with pytest.raises(DocumentLoadError, match="Could not read"):
        load_pages("broken.docx", b"not a zip file")
