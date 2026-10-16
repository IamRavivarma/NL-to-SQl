import pytest

from app.ingestion.loaders import MAX_FILE_BYTES, DocumentLoadError, Page, load_pages
from tests.files import make_docx, make_pdf


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


@pytest.mark.parametrize("filename", ["data.csv", "notes", "image.png"])
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
