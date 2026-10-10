from datetime import datetime

from beanie import Document
from pydantic import Field

from app.core.database import utcnow


class StoredDocument(Document):
    filename: str
    file_type: str
    size_bytes: int
    page_count: int
    chunk_count: int
    uploaded_at: datetime = Field(default_factory=utcnow)

    class Settings:
        name = "documents"
