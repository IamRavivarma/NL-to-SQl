import json

from beanie import PydanticObjectId
from langchain_core.messages import AIMessage

from app.api.deps import get_llm, get_store
from app.main import app
from app.models import Conversation, Message, StoredDocument
from app.rag.prompts import NO_DOCUMENTS_ANSWER
from tests.fakes import FailingChatModel, FakeChunkStore, RecordingChatModel, fake_llm, hit


def parse_sse(text: str) -> list[tuple[str, dict]]:
    events = []
    for block in text.strip().split("\n\n"):
        lines = dict(line.split(": ", 1) for line in block.split("\n"))
        events.append((lines["event"], json.loads(lines["data"])))
    return events


async def add_document():
    await StoredDocument(filename="guide.pdf", file_type="pdf", size_bytes=1, page_count=1, chunk_count=1).insert()


def override(store, llm):
    app.dependency_overrides[get_store] = lambda: store
    app.dependency_overrides[get_llm] = lambda: llm


async def test_query_streams_answer_and_persists_conversation(client):
    await add_document()
    override(FakeChunkStore(hits=[hit("Refunds take ten days.")]), fake_llm("Ten days [guide.pdf p.1]."))

    response = await client.post("/api/query", json={"question": "How long do refunds take?"})
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    events = parse_sse(response.text)

    names = [name for name, _ in events]
    assert names[0] == "meta" and names[-1] == "done" and set(names[1:-1]) == {"token"}
    conversation_id = events[0][1]["conversation_id"]
    assert "".join(data["text"] for name, data in events if name == "token") == "Ten days [guide.pdf p.1]."

    conversation = await Conversation.get(conversation_id)
    assert conversation.title == "How long do refunds take?"
    messages = await Message.find(Message.conversation_id == conversation.id).sort(+Message.created_at).to_list()
    assert [(m.role, m.content) for m in messages] == [
        ("user", "How long do refunds take?"),
        ("assistant", "Ten days [guide.pdf p.1]."),
    ]
    assert messages[1].sources[0].filename == "guide.pdf"
    assert messages[1].metrics.chunks_retrieved == 1
    assert events[-1][1]["message_id"] == str(messages[1].id)


async def test_follow_up_reuses_conversation_and_sends_history(client):
    await add_document()
    override(FakeChunkStore(hits=[hit("x")]), fake_llm("First answer."))
    first = parse_sse((await client.post("/api/query", json={"question": "First?"})).text)
    conversation_id = first[0][1]["conversation_id"]

    llm = RecordingChatModel(messages=iter([AIMessage(content="Second answer.")]))
    override(FakeChunkStore(hits=[hit("x")]), llm)
    second = parse_sse((await client.post("/api/query", json={"question": "Second?", "conversation_id": conversation_id})).text)
    assert second[0][1]["conversation_id"] == conversation_id
    assert await Message.find(Message.conversation_id == PydanticObjectId(conversation_id)).count() == 4
    prompt = [(m.type, m.content) for m in llm.received]
    assert ("human", "First?") in prompt and ("ai", "First answer.") in prompt


async def test_no_documents_short_circuits_without_llm(client):
    override(FakeChunkStore(), FailingChatModel(messages=iter([])))
    events = parse_sse((await client.post("/api/query", json={"question": "Hello?"})).text)
    assert [name for name, _ in events] == ["meta", "token", "done"]
    assert events[1][1]["text"] == NO_DOCUMENTS_ANSWER
    assert events[2][1]["metrics"] is None


async def test_llm_failure_emits_error_and_saves_error_message(client):
    await add_document()
    override(FakeChunkStore(hits=[hit("x")]), FailingChatModel(messages=iter([])))
    events = parse_sse((await client.post("/api/query", json={"question": "Q?"})).text)
    name, data = events[-1]
    assert name == "error"
    assert data["message"] == "Sorry, something went wrong while answering."
    assistant = await Message.find_one(Message.role == "assistant")
    assert assistant.status == "error"
    assert data["conversation_id"] == str(assistant.conversation_id)


async def test_unknown_conversation_returns_404(client):
    override(FakeChunkStore(), fake_llm("x"))
    response = await client.post("/api/query", json={"question": "Q?", "conversation_id": "650000000000000000000000"})
    assert response.status_code == 404


async def test_blank_or_too_long_question_returns_422(client):
    override(FakeChunkStore(), fake_llm("x"))
    assert (await client.post("/api/query", json={"question": "   "})).status_code == 422
    assert (await client.post("/api/query", json={"question": "x" * 2001})).status_code == 422
