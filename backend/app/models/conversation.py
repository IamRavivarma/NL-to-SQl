from datetime import datetime

from beanie import Document
from pydantic import Field

from app.core.database import utcnow


class Conversation(Document):
    title: str
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)

    class Settings:
        name = "conversations"
