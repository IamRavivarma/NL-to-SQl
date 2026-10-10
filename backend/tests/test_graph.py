import pytest
from langchain_core.messages import AIMessage

from app.rag.graph import build_sources, is_not_found, stream_answer
from app.rag.prompts import NOT_FOUND_ANSWER
from tests.fakes import FailingChatModel, FakeChunkStore, SlowStartChatModel, fake_llm, hit


async def collect(**kwargs):
    return [event async for event in stream_answer(model_name="test-model", **kwargs)]


def test_build_sources_dedupes_by_file_and_page_and_truncates_snippets():
    hits = [hit("A" * 500, "a.pdf", 1), hit("other chunk", "a.pdf", 1), hit("B", "b.pdf", 2)]
    sources = build_sources(hits)
    assert sources == [
        {"filename": "a.pdf", "page": 1, "snippet": "A" * 200},
        {"filename": "b.pdf", "page": 2, "snippet": "B"},
    ]


@pytest.mark.parametrize(
    "answer",
    ["I couldn't find that in your documents.", "I couldn\u2019t find that in your documents", "  i couldn't find that in your documents.  "],
)
def test_is_not_found_tolerates_apostrophes_case_and_period(answer):
    assert is_not_found(answer)


def test_is_not_found_false_for_real_answers():
    assert not is_not_found("Refunds take ten days [guide.pdf p.1].")


async def test_stream_emits_meta_tokens_done_in_order():
    store = FakeChunkStore(hits=[hit("Refunds take ten days.", "guide.pdf", 1)])
    events = await collect(
        question="How long do refunds take?", history=[], store=store, llm=fake_llm("Ten days [guide.pdf p.1].")
    )

    assert events[0] == {"type": "meta", "sources": [{"filename": "guide.pdf", "page": 1, "snippet": "Refunds take ten days."}]}
    tokens = [e["text"] for e in events if e["type"] == "token"]
    assert "".join(tokens) == "Ten days [guide.pdf p.1]."
    done = events[-1]
    assert done["type"] == "done"
    assert done["answer"] == "Ten days [guide.pdf p.1]."
    assert done["sources"] == events[0]["sources"]
    metrics = done["metrics"]
    assert metrics["model"] == "test-model"
    assert metrics["chunks_retrieved"] == 1
    assert metrics["output_tokens"] == 4  # whitespace estimate: no usage metadata from the fake model
    assert metrics["ttft_ms"] >= 0 and metrics["total_ms"] >= metrics["ttft_ms"]
    assert metrics["tokens_per_sec"] > 0
    assert store.queries == ["How long do refunds take?"]


async def test_tokens_per_sec_counts_time_before_first_token():
    # Reasoning models spend output tokens before the first visible token; that time must count.
    llm = SlowStartChatModel(messages=iter([AIMessage(content="one two three four")]), delay_seconds=0.2)
    events = await collect(question="Q?", history=[], store=FakeChunkStore(hits=[hit("x")]), llm=llm)
    metrics = events[-1]["metrics"]
    assert metrics["ttft_ms"] >= 200
    assert metrics["tokens_per_sec"] <= 4 / 0.2  # 4 tokens over at least 0.2 s of generation


async def test_not_found_answer_clears_sources():
    store = FakeChunkStore(hits=[hit("Unrelated text")])
    events = await collect(question="Who won the 1998 World Cup?", history=[], store=store, llm=fake_llm(NOT_FOUND_ANSWER))
    assert events[-1]["answer"] == NOT_FOUND_ANSWER
    assert events[-1]["sources"] == []


async def test_no_hits_still_answers():
    events = await collect(question="Anything?", history=[], store=FakeChunkStore(hits=[]), llm=fake_llm(NOT_FOUND_ANSWER))
    assert events[0] == {"type": "meta", "sources": []}
    assert events[-1]["type"] == "done"


async def test_llm_failure_propagates_after_meta():
    store = FakeChunkStore(hits=[hit("text")])
    stream = stream_answer("Q?", [], store=store, llm=FailingChatModel(messages=iter([])), model_name="m")
    first = await anext(stream)
    assert first["type"] == "meta"
    with pytest.raises(RuntimeError, match="groq unavailable"):
        async for _ in stream:
            pass
