import time
from collections.abc import AsyncIterator
from typing import TypedDict

from langchain_core.documents import Document
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage
from langgraph.graph import END, START, StateGraph
from starlette.concurrency import run_in_threadpool

from app.rag.prompts import HISTORY_LIMIT, NOT_FOUND_ANSWER, RAG_SYSTEM_PROMPT
from app.rag.vector_store import TOP_K

SNIPPET_CHARS = 200

Hit = tuple[Document, float]


class RagState(TypedDict, total=False):
    question: str
    history: list[tuple[str, str]]
    hits: list[Hit]
    answer: AIMessage


def build_sources(hits: list[Hit]) -> list[dict]:
    sources, seen = [], set()
    for doc, _score in hits:
        key = (doc.metadata["filename"], doc.metadata["page"])
        if key in seen:
            continue
        seen.add(key)
        snippet = " ".join(doc.page_content.split())[:SNIPPET_CHARS]
        sources.append({"filename": key[0], "page": key[1], "snippet": snippet})
    return sources


def _normalize(text: str) -> str:
    return text.strip().replace("\u2019", "'").rstrip(".").lower()


def is_not_found(answer: str) -> bool:
    return _normalize(answer) == _normalize(NOT_FOUND_ANSWER)


def _format_context(hits: list[Hit]) -> str:
    if not hits:
        return "(no excerpts found)"
    return "\n\n".join(
        f"[{i}] ({doc.metadata['filename']} p.{doc.metadata['page']})\n{doc.page_content}"
        for i, (doc, _score) in enumerate(hits, start=1)
    )


def build_graph(store, llm: BaseChatModel):
    async def retrieve(state: RagState) -> dict:
        hits = await run_in_threadpool(store.search, state["question"], TOP_K)
        return {"hits": hits}

    async def generate(state: RagState) -> dict:
        messages = [
            ("system", RAG_SYSTEM_PROMPT),
            *state["history"][-HISTORY_LIMIT:],
            ("human", f"Context excerpts:\n{_format_context(state['hits'])}\n\nQuestion: {state['question']}"),
        ]
        return {"answer": await llm.ainvoke(messages)}

    graph = StateGraph(RagState)
    graph.add_node("retrieve", retrieve)
    graph.add_node("generate", generate)
    graph.add_edge(START, "retrieve")
    graph.add_edge("retrieve", "generate")
    graph.add_edge("generate", END)
    return graph.compile()


async def stream_answer(
    question: str, history: list[tuple[str, str]], *, store, llm: BaseChatModel, model_name: str
) -> AsyncIterator[dict]:
    started = time.perf_counter()
    first_token_at: float | None = None
    sources: list[dict] = []
    chunks_retrieved = 0
    parts: list[str] = []
    final: AIMessage | None = None

    graph = build_graph(store, llm)
    async for mode, payload in graph.astream(
        {"question": question, "history": history}, stream_mode=["updates", "messages"]
    ):
        if mode == "updates":
            if "retrieve" in payload:
                hits = payload["retrieve"]["hits"]
                chunks_retrieved = len(hits)
                sources = build_sources(hits)
                yield {"type": "meta", "sources": sources}
            elif "generate" in payload:
                final = payload["generate"]["answer"]
        else:
            chunk, metadata = payload
            text = chunk.content if isinstance(chunk.content, str) else ""
            if metadata.get("langgraph_node") == "generate" and text:
                if first_token_at is None:
                    first_token_at = time.perf_counter()
                parts.append(text)
                yield {"type": "token", "text": text}

    finished = time.perf_counter()
    answer = "".join(parts) or (final.content if final is not None else "")
    if is_not_found(answer):
        sources = []

    usage = (final.usage_metadata if final is not None else None) or {}
    output_tokens = usage.get("output_tokens") or len(answer.split())
    generation_seconds = max(finished - (first_token_at or started), 1e-3)
    yield {
        "type": "done",
        "answer": answer,
        "sources": sources,
        "metrics": {
            "model": model_name,
            "ttft_ms": int(((first_token_at or finished) - started) * 1000),
            "total_ms": int((finished - started) * 1000),
            "output_tokens": output_tokens,
            "tokens_per_sec": round(output_tokens / generation_seconds, 1),
            "chunks_retrieved": chunks_retrieved,
        },
    }
