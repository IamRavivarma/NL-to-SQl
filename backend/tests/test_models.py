from app.models import Conversation, Message, Metrics, Source, StoredDocument


async def test_message_round_trip_with_sources_and_metrics(mongo):
    conversation = Conversation(title="What is in the handbook?")
    await conversation.insert()
    message = Message(
        conversation_id=conversation.id,
        role="assistant",
        content="Vacation is 20 days [handbook.pdf p.3].",
        sources=[Source(filename="handbook.pdf", page=3, snippet="Employees get 20 days")],
        metrics=Metrics(
            model="openai/gpt-oss-120b", ttft_ms=300, total_ms=900,
            output_tokens=40, tokens_per_sec=66.7, chunks_retrieved=4,
        ),
    )
    await message.insert()

    fetched = await Message.find_one(Message.conversation_id == conversation.id)
    assert fetched.sources[0].page == 3
    assert fetched.metrics.tokens_per_sec == 66.7
    assert fetched.status == "complete"
    assert fetched.created_at.tzinfo is not None


async def test_stored_document_defaults_uploaded_at(mongo):
    doc = StoredDocument(filename="a.txt", file_type="txt", size_bytes=10, page_count=1, chunk_count=1)
    await doc.insert()
    assert (await StoredDocument.get(doc.id)).uploaded_at is not None
