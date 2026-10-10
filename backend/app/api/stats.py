from collections import Counter

from fastapi import APIRouter

from app.models import Message, StoredDocument

router = APIRouter(prefix="/api", tags=["stats"])

PER_QUESTION_LIMIT = 50


@router.get("/stats")
async def stats():
    documents = await StoredDocument.find_all().to_list()
    questions = await Message.find(Message.role == "user").to_list()
    answered = (
        await Message.find(Message.role == "assistant", Message.status == "complete", Message.metrics != None)  # noqa: E711
        .sort(+Message.created_at)
        .to_list()
    )

    per_day = Counter(m.created_at.date().isoformat() for m in questions)
    return {
        "totals": {
            "documents": len(documents),
            "chunks": sum(d.chunk_count for d in documents),
            "questions": len(questions),
            "avg_tokens_per_sec": round(sum(m.metrics.tokens_per_sec for m in answered) / len(answered), 1)
            if answered
            else None,
            "avg_ttft_ms": round(sum(m.metrics.ttft_ms for m in answered) / len(answered)) if answered else None,
        },
        "per_question": [
            {
                "created_at": m.created_at.isoformat(),
                "ttft_ms": m.metrics.ttft_ms,
                "total_ms": m.metrics.total_ms,
                "tokens_per_sec": m.metrics.tokens_per_sec,
            }
            for m in answered[-PER_QUESTION_LIMIT:]
        ],
        "questions_per_day": [{"date": day, "count": per_day[day]} for day in sorted(per_day)],
        "chunks_per_document": [{"filename": d.filename, "chunks": d.chunk_count} for d in documents],
    }
