import pytest

from app.ingestion.loaders import Table
from app.rag.graph import stream_answer
from app.rag.prompts import SQL_ANSWER_PROMPT
from tests.fakes import FakeChunkStore, hit, scripted_llm

SALES = Table(sheet="Q1", page=1, header=["Region", "Revenue"], rows=[["North", 120000], ["South", 95000]])


@pytest.fixture
def sales_tables(table_store):
    table_store.create_tables("doc1", "sales.xlsx", [SALES])
    return table_store


async def collect(**kwargs):
    return [event async for event in stream_answer(model_name="test-model", history=[], **kwargs)]


def meta_of(events):
    return next(e for e in events if e["type"] == "meta")


async def test_without_tables_the_mongodb_query_is_reported(table_store):
    store = FakeChunkStore(hits=[hit("Refunds take ten days.", "guide.pdf", 1, score=0.91234)])
    llm = scripted_llm("Ten days [guide.pdf p.1].")
    events = await collect(question="How long do refunds take?", store=store, llm=llm, tables=table_store)

    assert len(llm.calls) == 1  # no planner call when there are no tables
    [run] = meta_of(events)["queries"]
    assert run["kind"] == "mongodb"
    assert '"$vectorSearch"' in run["query"]
    assert '"numCandidates": 100' in run["query"] and '"limit": 4' in run["query"]
    assert "<384 numbers from your question>" in run["query"]
    assert run["columns"] == ["File", "Page", "Score", "Excerpt"]
    assert run["rows"] == [["guide.pdf", 1, 0.912, "Refunds take ten days."]]
    assert run["row_count"] == 1
    assert events[-1]["queries"] == [run]


async def test_sql_question_runs_the_query_and_skips_document_search(sales_tables):
    store = FakeChunkStore(hits=[hit("unused")])
    llm = scripted_llm('{"sql": "SELECT SUM(revenue) AS total FROM sales_q1"}', "Total revenue is 215000 [sales.xlsx p.1].")
    events = await collect(question="What is the total revenue?", store=store, llm=llm, tables=sales_tables)

    assert store.queries == []
    meta = meta_of(events)
    assert meta["queries"] == [
        {
            "kind": "sql",
            "query": "SELECT SUM(revenue) AS total FROM sales_q1",
            "columns": ["total"],
            "rows": [[215000]],
            "row_count": 1,
            "truncated": False,
            "error": None,
            "tables": [{"filename": "sales.xlsx", "page": 1}],
        }
    ]
    assert meta["sources"] == [{"filename": "sales.xlsx", "page": 1, "snippet": "Rows returned by the SQL query"}]
    planner_prompt = llm.calls[0][0].content
    assert "sales_q1" in planner_prompt and "revenue INTEGER" in planner_prompt
    answer_messages = llm.calls[1]
    assert answer_messages[0].content == SQL_ANSWER_PROMPT
    assert "215000" in answer_messages[-1].content and "sales.xlsx p.1" in answer_messages[-1].content
    done = events[-1]
    assert done["answer"] == "Total revenue is 215000 [sales.xlsx p.1]."
    assert done["queries"] == meta["queries"]
    assert done["metrics"]["chunks_retrieved"] == 0


async def test_planner_tokens_are_not_streamed_as_answer_text(sales_tables):
    llm = scripted_llm('{"sql": "SELECT region FROM sales_q1"}', "North and South.")
    events = await collect(question="Which regions?", store=FakeChunkStore(), llm=llm, tables=sales_tables)
    assert "".join(e["text"] for e in events if e["type"] == "token") == "North and South."


async def test_question_not_about_tables_falls_back_to_document_search(sales_tables):
    store = FakeChunkStore(hits=[hit("Refunds take ten days.")])
    llm = scripted_llm('{"sql": null}', "Ten days [guide.pdf p.1].")
    events = await collect(question="How long do refunds take?", store=store, llm=llm, tables=sales_tables)

    assert [q["kind"] for q in meta_of(events)["queries"]] == ["mongodb"]
    assert store.queries == ["How long do refunds take?"]


async def test_failed_sql_is_retried_with_the_error(sales_tables):
    llm = scripted_llm(
        '{"sql": "SELECT nope FROM sales_q1"}', '{"sql": "SELECT region FROM sales_q1"}', "North and South."
    )
    events = await collect(question="Which regions?", store=FakeChunkStore(), llm=llm, tables=sales_tables)

    [run] = meta_of(events)["queries"]
    assert run["query"] == "SELECT region FROM sales_q1"
    assert run["error"] is None and run["rows"] == [["North"], ["South"]]
    assert len(llm.calls) == 3
    assert "no such column: nope" in llm.calls[1][-1].content


async def test_sql_failing_twice_falls_back_and_shows_both_queries(sales_tables):
    store = FakeChunkStore(hits=[hit("Some text")])
    llm = scripted_llm('{"sql": "SELECT nope FROM sales_q1"}', '{"sql": "SELECT still_nope FROM sales_q1"}', "Answer.")
    events = await collect(question="Q?", store=store, llm=llm, tables=sales_tables)

    sql_run, mongo_run = meta_of(events)["queries"]
    assert sql_run["kind"] == "sql" and sql_run["query"] == "SELECT still_nope FROM sales_q1"
    assert "no such column: still_nope" in sql_run["error"]
    assert sql_run["rows"] == [] and sql_run["columns"] == []
    assert mongo_run["kind"] == "mongodb"
    assert store.queries == ["Q?"]


async def test_unsafe_sql_is_never_run(sales_tables):
    llm = scripted_llm('{"sql": "DELETE FROM sales_q1"}', '{"sql": null}', "Answer.")
    events = await collect(question="Delete everything", store=FakeChunkStore(), llm=llm, tables=sales_tables)

    sql_run, _ = meta_of(events)["queries"]
    assert sql_run["error"] == "Only SELECT queries are allowed."
    assert sales_tables.catalog()[0].row_count == 2
    assert len(sales_tables.run_select("SELECT * FROM sales_q1").rows) == 2


async def test_displayed_rows_are_capped_at_50(table_store):
    table_store.create_tables("doc1", "big.csv", [Table(sheet=None, page=1, header=["N"], rows=[[i] for i in range(120)])])
    llm = scripted_llm('{"sql": "SELECT n FROM big"}', "Many rows.")
    events = await collect(question="List all", store=FakeChunkStore(), llm=llm, tables=table_store)

    [run] = meta_of(events)["queries"]
    assert len(run["rows"]) == 50
    assert run["row_count"] == 120 and run["truncated"] is False
