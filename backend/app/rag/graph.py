import json
import re
import time
from collections.abc import AsyncIterator
from typing import TypedDict

from langchain_core.documents import Document
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage
from langgraph.graph import END, START, StateGraph
from starlette.concurrency import run_in_threadpool

from app.rag.prompts import (
    HISTORY_LIMIT,
    NOT_FOUND_ANSWER,
    RAG_SYSTEM_PROMPT,
    SQL_ANSWER_PROMPT,
    SQL_FIX_PROMPT,
    SQL_PLANNER_PROMPT,
)
from app.rag.vector_store import OVERSAMPLING_FACTOR, TOP_K, VECTOR_INDEX_NAME
from app.sql.planner import describe_schema, parse_sql_plan
from app.sql.table_store import QueryResult, SqlError, TableInfo

SNIPPET_CHARS = 200
DISPLAY_ROWS = 50
SQL_SOURCE_SNIPPET = "Rows returned by the SQL query"

Hit = tuple[Document, float]


class RagState(TypedDict, total=False):
    question: str
    history: list[tuple[str, str]]
    sql_runs: list[dict]
    sql_ok: bool
    hits: list[Hit]
    answer: AIMessage


def build_sources(hits: list[Hit]) -> list[dict]:
    sources, seen = [], set()
    for doc, _score in hits:
        key = (doc.metadata["filename"], doc.metadata["page"])
        if key in seen:
            continue
        seen.add(key)
        sources.append({"filename": key[0], "page": key[1], "snippet": _snippet(doc.page_content)})
    return sources


def _snippet(text: str) -> str:
    return " ".join(text.split())[:SNIPPET_CHARS]


def mongodb_query_run(hits: list[Hit]) -> dict:
    """The aggregation pipeline langchain-mongodb runs for a similarity search, and the chunks it returned."""
    pipeline = [
        {
            "$vectorSearch": {
                "index": VECTOR_INDEX_NAME,
                "path": "embedding",
                "queryVector": "<384 numbers from your question>",
                "numCandidates": TOP_K * OVERSAMPLING_FACTOR,
                "limit": TOP_K,
            }
        },
        {"$set": {"score": {"$meta": "vectorSearchScore"}}},
        {"$project": {"embedding": 0}},
    ]
    return {
        "kind": "mongodb",
        "query": f"db.chunks.aggregate({json.dumps(pipeline, indent=2)})",
        "columns": ["File", "Page", "Score", "Excerpt"],
        "rows": [
            [doc.metadata["filename"], doc.metadata["page"], round(score, 3), _snippet(doc.page_content)]
            for doc, score in hits
        ],
        "row_count": len(hits),
    }


def sql_query_run(sql: str, result: QueryResult | None, error: str | None, tables: list[dict]) -> dict:
    return {
        "kind": "sql",
        "query": sql,
        "columns": result.columns if result else [],
        "rows": result.rows[:DISPLAY_ROWS] if result else [],
        "row_count": len(result.rows) if result else 0,
        "truncated": result.truncated if result else False,
        "error": error,
        "tables": tables,
    }


def _tables_in(sql: str, catalog: list[TableInfo]) -> list[dict]:
    used = []
    for info in catalog:
        source = {"filename": info.filename, "page": info.page}
        if re.search(rf"\b{re.escape(info.table_name)}\b", sql, re.IGNORECASE) and source not in used:
            used.append(source)
    return used


def _sql_sources(run: dict) -> list[dict]:
    return [{**table, "snippet": SQL_SOURCE_SNIPPET} for table in run["tables"]]


# gpt-oss cites with fullwidth lenticular brackets; the app's citation format is [filename p.N].
# Each bracket is one character, so translating streamed tokens one at a time is safe.
_CITATION_BRACKETS = str.maketrans({"【": "[", "】": "]"})


def _square_citations(text: str) -> str:
    return text.translate(_CITATION_BRACKETS)


def _normalize(text: str) -> str:
    return text.strip().replace("’", "'").rstrip(".").lower()


def is_not_found(answer: str) -> bool:
    return _normalize(answer) == _normalize(NOT_FOUND_ANSWER)


def _format_context(hits: list[Hit]) -> str:
    if not hits:
        return "(no excerpts found)"
    return "\n\n".join(
        f"[{i}] ({doc.metadata['filename']} p.{doc.metadata['page']})\n{doc.page_content}"
        for i, (doc, _score) in enumerate(hits, start=1)
    )


def _format_sql_result(run: dict) -> str:
    sources = ", ".join(f"{t['filename']} p.{t['page']}" for t in run["tables"]) or "(unknown)"
    if run["row_count"] > len(run["rows"]):
        count = f"{run['row_count']}{'+' if run['truncated'] else ''} rows, first {len(run['rows'])} shown"
    else:
        count = f"{run['row_count']} rows"
    lines = [f"| {' | '.join(run['columns'])} |", f"|{' --- |' * len(run['columns'])}"]
    lines += [f"| {' | '.join('' if v is None else str(v) for v in row)} |" for row in run["rows"]]
    return f"SQL query:\n{run['query']}\n\nSource tables: {sources}\n\nResult ({count}):\n" + "\n".join(lines)


def _content(message: AIMessage) -> str:
    return message.content if isinstance(message.content, str) else ""


def build_graph(store, llm: BaseChatModel, tables=None):
    async def run_sql(sql: str) -> tuple[QueryResult | None, str | None]:
        try:
            return await run_in_threadpool(tables.run_select, sql), None
        except SqlError as exc:
            return None, str(exc)

    async def plan_sql(state: RagState) -> dict:
        catalog = await run_in_threadpool(tables.catalog) if tables is not None else []
        if not catalog:
            return {"sql_runs": [], "sql_ok": False}
        samples = {info.table_name: await run_in_threadpool(tables.sample_rows, info.table_name) for info in catalog}
        messages = [
            ("system", SQL_PLANNER_PROMPT.format(schema=describe_schema(catalog, samples))),
            *state["history"][-HISTORY_LIMIT:],
            ("human", state["question"]),
        ]
        reply = await llm.ainvoke(messages)
        sql = parse_sql_plan(_content(reply))
        if sql is None:
            return {"sql_runs": [], "sql_ok": False}
        result, error = await run_sql(sql)
        if error is not None:
            # One chance to correct the query using the database's error message.
            messages += [("ai", _content(reply)), ("human", SQL_FIX_PROMPT.format(error=error))]
            fixed = parse_sql_plan(_content(await llm.ainvoke(messages)))
            if fixed is not None:
                sql = fixed
                result, error = await run_sql(sql)
        return {"sql_runs": [sql_query_run(sql, result, error, _tables_in(sql, catalog))], "sql_ok": error is None}

    async def retrieve(state: RagState) -> dict:
        hits = await run_in_threadpool(store.search, state["question"], TOP_K)
        return {"hits": hits}

    async def generate(state: RagState) -> dict:
        if state.get("sql_ok"):
            system, context = SQL_ANSWER_PROMPT, _format_sql_result(state["sql_runs"][-1])
        else:
            system, context = RAG_SYSTEM_PROMPT, f"Context excerpts:\n{_format_context(state['hits'])}"
        messages = [
            ("system", system),
            *state["history"][-HISTORY_LIMIT:],
            ("human", f"{context}\n\nQuestion: {state['question']}"),
        ]
        return {"answer": await llm.ainvoke(messages)}

    graph = StateGraph(RagState)
    graph.add_node("plan_sql", plan_sql)
    graph.add_node("retrieve", retrieve)
    graph.add_node("generate", generate)
    graph.add_edge(START, "plan_sql")
    graph.add_conditional_edges("plan_sql", lambda state: "generate" if state["sql_ok"] else "retrieve")
    graph.add_edge("retrieve", "generate")
    graph.add_edge("generate", END)
    return graph.compile()


async def stream_answer(
    question: str, history: list[tuple[str, str]], *, store, llm: BaseChatModel, model_name: str, tables=None
) -> AsyncIterator[dict]:
    started = time.perf_counter()
    generation_started = started
    first_token_at: float | None = None
    sources: list[dict] = []
    queries: list[dict] = []
    sql_runs: list[dict] = []
    chunks_retrieved = 0
    parts: list[str] = []
    final: AIMessage | None = None

    graph = build_graph(store, llm, tables)
    async for mode, payload in graph.astream(
        {"question": question, "history": history}, stream_mode=["updates", "messages"]
    ):
        if mode == "updates":
            if "plan_sql" in payload:
                sql_runs = payload["plan_sql"]["sql_runs"]
                if payload["plan_sql"]["sql_ok"]:
                    queries, sources = sql_runs, _sql_sources(sql_runs[-1])
                    generation_started = time.perf_counter()
                    yield {"type": "meta", "sources": sources, "queries": queries}
            elif "retrieve" in payload:
                hits = payload["retrieve"]["hits"]
                chunks_retrieved = len(hits)
                sources = build_sources(hits)
                queries = [*sql_runs, mongodb_query_run(hits)]
                generation_started = time.perf_counter()
                yield {"type": "meta", "sources": sources, "queries": queries}
            elif "generate" in payload:
                final = payload["generate"]["answer"]
        else:
            chunk, metadata = payload
            text = _square_citations(chunk.content) if isinstance(chunk.content, str) else ""
            if metadata.get("langgraph_node") == "generate" and text:
                if first_token_at is None:
                    first_token_at = time.perf_counter()
                parts.append(text)
                yield {"type": "token", "text": text}

    finished = time.perf_counter()
    answer = "".join(parts) or _square_citations(final.content if final is not None else "")
    if is_not_found(answer):
        sources = []

    usage = (final.usage_metadata if final is not None else None) or {}
    output_tokens = usage.get("output_tokens") or len(answer.split())
    # From the LLM call's start, not the first visible token: reasoning models spend output tokens
    # (counted in usage) before any answer text appears.
    generation_seconds = max(finished - generation_started, 1e-3)
    yield {
        "type": "done",
        "answer": answer,
        "sources": sources,
        "queries": queries,
        "metrics": {
            "model": model_name,
            "ttft_ms": int(((first_token_at or finished) - started) * 1000),
            "total_ms": int((finished - started) * 1000),
            "output_tokens": output_tokens,
            "tokens_per_sec": round(output_tokens / generation_seconds, 1),
            "chunks_retrieved": chunks_retrieved,
        },
    }
