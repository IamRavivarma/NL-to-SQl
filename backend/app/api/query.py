import asyncio
import logging

import anyio
from beanie import PydanticObjectId
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field, field_validator

from app.api.deps import get_llm, get_store, get_tables
from app.api.sse import format_sse
from app.core.config import settings
from app.core.database import utcnow
from app.models import Conversation, Message, Metrics, Source, StoredDocument
from app.rag.graph import stream_answer
from app.rag.prompts import HISTORY_LIMIT, NO_DOCUMENTS_ANSWER

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api", tags=["query"])

ERROR_MESSAGE = "Sorry, something went wrong while answering."
TITLE_CHARS = 60


class QueryRequest(BaseModel):
    question: str = Field(max_length=2000)
    conversation_id: PydanticObjectId | None = None
    # The file selected in the sidebar: searched first and preferred. None treats every document the same.
    document_id: PydanticObjectId | None = None

    @field_validator("question")
    @classmethod
    def not_blank(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Question must not be empty")
        return value


async def _load_history(conversation_id: PydanticObjectId) -> list[tuple[str, str]]:
    recent = (
        await Message.find(Message.conversation_id == conversation_id, Message.status == "complete")
        .sort(-Message.created_at)
        .limit(HISTORY_LIMIT)
        .to_list()
    )
    return [("human" if m.role == "user" else "ai", m.content) for m in reversed(recent)]


async def _save_assistant(
    conversation: Conversation, content: str, sources, metrics, status: str, queries=None
) -> Message:
    message = Message(
        conversation_id=conversation.id,
        role="assistant",
        content=content,
        sources=[Source(**s) for s in sources],
        metrics=Metrics(**metrics) if metrics else None,
        queries=queries or [],
        status=status,
    )
    await message.insert()
    conversation.updated_at = utcnow()
    await conversation.save()
    return message


@router.post("/query")
async def query(request: QueryRequest, store=Depends(get_store), llm=Depends(get_llm), tables=Depends(get_tables)):
    document = None
    if request.document_id is not None:
        document = await StoredDocument.get(request.document_id)
        if document is None:
            raise HTTPException(status_code=404, detail="Document not found")

    if request.conversation_id is not None:
        conversation = await Conversation.get(request.conversation_id)
        if conversation is None:
            raise HTTPException(status_code=404, detail="Conversation not found")
    else:
        conversation = Conversation(title=request.question[:TITLE_CHARS])
        await conversation.insert()

    history = await _load_history(conversation.id)
    await Message(
        conversation_id=conversation.id,
        role="user",
        content=request.question,
        document_filename=document.filename if document else None,
    ).insert()

    return StreamingResponse(
        _events(
            conversation,
            request.question,
            history,
            store,
            llm,
            tables,
            str(document.id) if document else None,
            document.filename if document else None,
        ),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


async def _events(
    conversation: Conversation, question: str, history, store, llm, tables=None, document_id=None, document_filename=None
):
    conversation_id = str(conversation.id)
    partial: list[str] = []
    queries: list[dict] = []
    saved = False
    try:
        if await StoredDocument.count() == 0:
            yield format_sse("meta", {"conversation_id": conversation_id, "sources": [], "queries": []})
            yield format_sse("token", {"text": NO_DOCUMENTS_ANSWER})
            message = await _save_assistant(conversation, NO_DOCUMENTS_ANSWER, [], None, "complete")
            saved = True
            yield format_sse("done", {"message_id": str(message.id), "metrics": None, "sources": [], "queries": []})
            return

        async for event in stream_answer(
            question,
            history,
            store=store,
            llm=llm,
            model_name=settings.groq_model,
            tables=tables,
            document_id=document_id,
            document_filename=document_filename,
        ):
            if event["type"] == "meta":
                queries = event["queries"]
                yield format_sse(
                    "meta", {"conversation_id": conversation_id, "sources": event["sources"], "queries": queries}
                )
            elif event["type"] == "token":
                partial.append(event["text"])
                yield format_sse("token", {"text": event["text"]})
            else:
                message = await _save_assistant(
                    conversation, event["answer"], event["sources"], event["metrics"], "complete", event["queries"]
                )
                saved = True
                yield format_sse(
                    "done",
                    {
                        "message_id": str(message.id),
                        "metrics": event["metrics"],
                        "sources": event["sources"],
                        "queries": event["queries"],
                    },
                )
    except (GeneratorExit, asyncio.CancelledError):
        # The client went away mid-answer (e.g. closed the tab). Keep what was streamed so the
        # conversation doesn't show an unanswered question; shield the save from the cancellation.
        if not saved:
            with anyio.CancelScope(shield=True):
                try:
                    await _save_assistant(conversation, "".join(partial), [], None, "error", queries)
                except Exception:
                    logger.exception("Could not save the interrupted answer for conversation %s", conversation_id)
        raise
    except Exception:
        logger.exception("Answering failed for conversation %s", conversation_id)
        try:
            await _save_assistant(conversation, "".join(partial), [], None, "error", queries)
        except Exception:
            logger.exception("Could not save the failed answer for conversation %s", conversation_id)
        yield format_sse("error", {"message": ERROR_MESSAGE, "conversation_id": conversation_id})
