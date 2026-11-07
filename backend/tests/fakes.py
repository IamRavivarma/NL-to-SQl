import time

from langchain_core.documents import Document
from langchain_core.language_models import GenericFakeChatModel
from langchain_core.messages import AIMessage


class FakeChunkStore:
    """In-memory stand-in for app.rag.vector_store.ChunkStore."""

    def __init__(self, hits=None, fail_on_add=False, fail_on_delete=False):
        self.hits = hits or []
        self.fail_on_add = fail_on_add
        self.fail_on_delete = fail_on_delete
        self.added: list[tuple[str, dict]] = []
        self.deleted: list[str] = []
        self.queries: list[str] = []

    def add_chunks(self, texts, metadatas):
        if self.fail_on_add:
            raise RuntimeError("vector store unavailable")
        self.added.extend(zip(texts, metadatas))

    def delete_document(self, document_id):
        if self.fail_on_delete:
            raise RuntimeError("vector store unavailable")
        self.deleted.append(document_id)
        return 1

    def search(self, query, k=4):
        self.queries.append(query)
        return self.hits[:k]


def hit(text, filename="guide.pdf", page=1, score=0.9):
    metadata = {"filename": filename, "page": page, "document_id": "doc1", "chunk_index": 0}
    return Document(page_content=text, metadata=metadata), score


def fake_llm(answer: str) -> GenericFakeChatModel:
    """Chat model that streams `answer` word by word (no usage metadata)."""
    return GenericFakeChatModel(messages=iter([AIMessage(content=answer)]))


class RecordingChatModel(GenericFakeChatModel):
    """Fake chat model that also records the messages it was called with."""

    received: list = []

    def _stream(self, messages, *args, **kwargs):
        self.received = list(messages)
        yield from super()._stream(messages, *args, **kwargs)


class ScriptedChatModel(GenericFakeChatModel):
    """Fake chat model that gives `replies` in order, one per call, and records every call's messages."""

    calls: list = []

    def _generate(self, messages, *args, **kwargs):
        self.calls = [*self.calls, list(messages)]
        return super()._generate(messages, *args, **kwargs)


def scripted_llm(*replies: str) -> ScriptedChatModel:
    return ScriptedChatModel(messages=iter([AIMessage(content=reply) for reply in replies]))


class SlowStartChatModel(GenericFakeChatModel):
    """Fake chat model that pauses before its first token, like a model that reasons before answering."""

    delay_seconds: float = 0.2

    def _stream(self, *args, **kwargs):
        time.sleep(self.delay_seconds)
        yield from super()._stream(*args, **kwargs)


class FailingChatModel(GenericFakeChatModel):
    """Chat model whose every call raises, to exercise error paths."""

    def _generate(self, *args, **kwargs):
        raise RuntimeError("groq unavailable")

    def _stream(self, *args, **kwargs):
        raise RuntimeError("groq unavailable")
