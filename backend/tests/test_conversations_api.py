from app.models import Conversation, Message


async def make_conversation(title):
    conversation = Conversation(title=title)
    await conversation.insert()
    await Message(conversation_id=conversation.id, role="user", content=title).insert()
    await Message(conversation_id=conversation.id, role="assistant", content="answer").insert()
    return conversation


async def test_list_conversations_newest_first(client):
    older = await make_conversation("older")
    newer = await make_conversation("newer")
    body = (await client.get("/api/conversations")).json()
    assert [c["id"] for c in body] == [str(newer.id), str(older.id)]
    assert body[0]["title"] == "newer"


async def test_get_conversation_returns_messages_in_order(client):
    conversation = await make_conversation("hello")
    body = (await client.get(f"/api/conversations/{conversation.id}")).json()
    assert body["title"] == "hello"
    assert [m["role"] for m in body["messages"]] == ["user", "assistant"]


async def test_delete_conversation_removes_messages(client):
    conversation = await make_conversation("bye")
    assert (await client.delete(f"/api/conversations/{conversation.id}")).status_code == 204
    assert await Conversation.count() == 0
    assert await Message.count() == 0


async def test_unknown_conversation_404(client):
    assert (await client.get("/api/conversations/650000000000000000000000")).status_code == 404
    assert (await client.delete("/api/conversations/650000000000000000000000")).status_code == 404
