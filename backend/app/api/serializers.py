from app.models import Conversation, Message, StoredDocument


def serialize_document(doc: StoredDocument) -> dict:
    return {
        "id": str(doc.id),
        "filename": doc.filename,
        "file_type": doc.file_type,
        "size_bytes": doc.size_bytes,
        "page_count": doc.page_count,
        "chunk_count": doc.chunk_count,
        "uploaded_at": doc.uploaded_at.isoformat(),
    }


def serialize_message(message: Message) -> dict:
    return {
        "id": str(message.id),
        "role": message.role,
        "content": message.content,
        "sources": [source.model_dump() for source in message.sources],
        "metrics": message.metrics.model_dump() if message.metrics else None,
        "queries": message.queries,
        "document_filename": message.document_filename,
        "status": message.status,
        "created_at": message.created_at.isoformat(),
    }


def serialize_conversation(conversation: Conversation) -> dict:
    return {
        "id": str(conversation.id),
        "title": conversation.title,
        "updated_at": conversation.updated_at.isoformat(),
    }
