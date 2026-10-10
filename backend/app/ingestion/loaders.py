from dataclasses import dataclass
from io import BytesIO
from pathlib import PurePath

import docx2txt
from pypdf import PdfReader

MAX_FILE_BYTES = 20 * 1024 * 1024
SUPPORTED_TYPES = ("pdf", "txt", "docx")


class DocumentLoadError(ValueError):
    """Raised with a message that can be shown to the user as-is."""


@dataclass(frozen=True)
class Page:
    text: str
    page_number: int  # 1-based


def detect_file_type(filename: str) -> str:
    file_type = PurePath(filename or "").suffix.lower().lstrip(".")
    if file_type not in SUPPORTED_TYPES:
        raise DocumentLoadError("Unsupported file type. Upload a PDF, TXT or DOCX file.")
    return file_type


def load_pages(filename: str, content: bytes) -> tuple[str, list[Page]]:
    file_type = detect_file_type(filename)
    if not content:
        raise DocumentLoadError("The file is empty.")
    if len(content) > MAX_FILE_BYTES:
        raise DocumentLoadError("The file is larger than 20 MB.")

    if file_type == "pdf":
        pages = _load_pdf(content)
    elif file_type == "docx":
        pages = [Page(text=_load_docx(content), page_number=1)]
    else:
        pages = [Page(text=_decode_text(content), page_number=1)]

    pages = [page for page in pages if page.text.strip()]
    if not pages:
        raise DocumentLoadError("No readable text found — scanned PDFs aren't supported.")
    return file_type, pages


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


def _decode_text(content: bytes) -> str:
    try:
        return content.decode("utf-8-sig")
    except UnicodeDecodeError:
        # Windows-1252 is the usual non-UTF-8 encoding for text files saved on Windows.
        return content.decode("cp1252", errors="replace")
