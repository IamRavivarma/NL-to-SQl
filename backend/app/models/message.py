from datetime import datetime
from typing import Annotated, Literal

from beanie import Document, Indexed, PydanticObjectId
from pydantic import BaseModel, Field

from app.core.database import utcnow


class Source(BaseModel):
    filename: str
    page: int
    snippet: str


class Metrics(BaseModel):
    model: str
    ttft_ms: int
    total_ms: int
    output_tokens: int
    tokens_per_sec: float
    chunks_retrieved: int


class Message(Document):
    conversation_id: Annotated[PydanticObjectId, Indexed()]
    role: Literal["user", "assistant"]
    content: str
    sources: list[Source] = Field(default_factory=list)
    metrics: Metrics | None = None
    # The database queries behind the answer (SQL over spreadsheets, or the MongoDB vector search), as shown in the UI.
    queries: list[dict] = Field(default_factory=list)
    # On a question: the file it was asked about (selected in the sidebar); None means all documents.
    document_filename: str | None = None
    status: Literal["complete", "error"] = "complete"
    created_at: datetime = Field(default_factory=utcnow)

    class Settings:
        name = "messages"
