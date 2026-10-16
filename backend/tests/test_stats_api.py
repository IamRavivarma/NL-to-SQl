from datetime import datetime, timezone

from app.models import Conversation, Message, Metrics, StoredDocument


def metrics(ttft, tps):
    return Metrics(model="m", ttft_ms=ttft, total_ms=ttft + 500, output_tokens=100, tokens_per_sec=tps, chunks_retrieved=4)


async def test_stats_empty(client):
    body = (await client.get("/api/stats")).json()
    assert body["totals"] == {"documents": 0, "chunks": 0, "questions": 0, "avg_tokens_per_sec": None, "avg_ttft_ms": None}
    assert body["per_question"] == [] and body["questions_per_day"] == [] and body["chunks_per_document"] == []


async def test_questions_per_day_uses_the_browsers_time_zone(client):
    conversation = Conversation(title="t")
    await conversation.insert()
    # 20:00 UTC on the 9th is 01:30 on the 10th in India (UTC+5:30, getTimezoneOffset() == -330).
    late = datetime(2026, 10, 9, 20, tzinfo=timezone.utc)
    await Message(conversation_id=conversation.id, role="user", content="q", created_at=late).insert()

    utc = (await client.get("/api/stats")).json()["questions_per_day"]
    india = (await client.get("/api/stats", params={"tz_offset_minutes": -330})).json()["questions_per_day"]
    assert utc == [{"date": "2026-10-09", "count": 1}]
    assert india == [{"date": "2026-10-10", "count": 1}]


async def test_stats_aggregates_documents_questions_and_metrics(client):
    await StoredDocument(filename="a.pdf", file_type="pdf", size_bytes=1, page_count=1, chunk_count=10).insert()
    await StoredDocument(filename="b.txt", file_type="txt", size_bytes=1, page_count=1, chunk_count=5).insert()
    conversation = Conversation(title="t")
    await conversation.insert()
    day1 = datetime(2026, 10, 9, 12, tzinfo=timezone.utc)
    day2 = datetime(2026, 10, 10, 12, tzinfo=timezone.utc)
    cid = conversation.id
    await Message(conversation_id=cid, role="user", content="q1", created_at=day1).insert()
    await Message(conversation_id=cid, role="assistant", content="a1", metrics=metrics(200, 400.0), created_at=day1).insert()
    await Message(conversation_id=cid, role="user", content="q2", created_at=day2).insert()
    await Message(conversation_id=cid, role="assistant", content="a2", metrics=metrics(400, 600.0), created_at=day2).insert()
    await Message(conversation_id=cid, role="user", content="q3", created_at=day2).insert()
    await Message(conversation_id=cid, role="assistant", content="", status="error", created_at=day2).insert()

    body = (await client.get("/api/stats")).json()
    assert body["totals"] == {"documents": 2, "chunks": 15, "questions": 3, "avg_tokens_per_sec": 500.0, "avg_ttft_ms": 300}
    assert [p["ttft_ms"] for p in body["per_question"]] == [200, 400]
    assert body["questions_per_day"] == [{"date": "2026-10-09", "count": 1}, {"date": "2026-10-10", "count": 2}]
    assert sorted(body["chunks_per_document"], key=lambda d: d["filename"]) == [
        {"filename": "a.pdf", "chunks": 10},
        {"filename": "b.txt", "chunks": 5},
    ]
