import math

from app.rag.embeddings import EMBEDDING_DIMENSIONS, get_embeddings


def test_embeddings_are_384_dim_and_normalized():
    vector = get_embeddings().embed_query("What is retrieval-augmented generation?")
    assert len(vector) == EMBEDDING_DIMENSIONS == 384
    assert math.isclose(math.sqrt(sum(v * v for v in vector)), 1.0, rel_tol=1e-3)


def test_similar_texts_score_higher_than_unrelated():
    emb = get_embeddings()
    query, close, far = emb.embed_documents(
        ["How do I reset my password?", "Steps to change your account password", "The cat sat on the mat"]
    )
    dot = lambda a, b: sum(x * y for x, y in zip(a, b))
    assert dot(query, close) > dot(query, far)
