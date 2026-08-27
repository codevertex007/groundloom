import pytest
from app.ai.retrieval.providers.reranking import (
    CohereCompatibleReranker,
    DeterministicReranker,
    build_reranker,
    combine_rerank_scores,
)
from app.config import Settings
from app.errors import GroundloomError


def test_deterministic_reranker_is_stable_bounded_and_phrase_aware():
    reranker = DeterministicReranker()
    documents = [
        "The torque service fastener uses 10 Nm.",
        "A general maintenance note.",
        "The torque service fastener uses 10 Nm.\nRepeated context.",
    ]
    first = reranker.score("torque service fastener", documents)
    second = reranker.score("torque service fastener", documents)
    assert first == second
    assert first[0] > first[1]
    assert all(0.0 <= score <= 1.0 for score in first)
    assert combine_rerank_scores(0.8, first[0]) <= 1.0


def test_cohere_compatible_reranker_orders_and_validates_response(monkeypatch):
    calls = []

    class Reranker:
        def compress_documents(self, documents, query):
            calls.append((query, [document.page_content for document in documents]))
            documents[0].metadata["relevance_score"] = 0.9
            documents[1].metadata["relevance_score"] = 0.2
            return [documents[0], documents[1]]

    reranker = CohereCompatibleReranker(
        api_key="secret-do-not-log",
        base_url="https://rerank.example",
        model="rerank-test",
        reranker=Reranker(),
    )
    assert reranker.score("query", ["first", "second"]) == [0.9, 0.2]
    assert calls == [("query", ["first", "second"])]

    class BadReranker:
        def compress_documents(self, documents, _query):
            documents[0].metadata["groundloom_index"] = 3
            documents[0].metadata["relevance_score"] = 0.4
            return [documents[0]]

    bad_reranker = CohereCompatibleReranker(
        api_key="secret-do-not-log",
        base_url="https://rerank.example",
        model="rerank-test",
        reranker=BadReranker(),
    )
    with pytest.raises(GroundloomError) as invalid:
        bad_reranker.score("query", ["one"])
    assert invalid.value.code == "PROVIDER_INVALID_RESPONSE"


def test_reranker_outage_and_missing_configuration_are_typed():
    class UnavailableReranker:
        def compress_documents(self, _documents, _query):
            raise RuntimeError("secret")

    reranker = CohereCompatibleReranker(
        api_key="secret-do-not-log",
        base_url="https://rerank.example",
        model="rerank-test",
        reranker=UnavailableReranker(),
    )
    with pytest.raises(GroundloomError) as outage:
        reranker.score("query", ["one"])
    assert outage.value.code == "DEPENDENCY_UNAVAILABLE"
    assert outage.value.retryable is True

    with pytest.raises(GroundloomError) as missing:
        build_reranker(Settings(reranker_provider="cohere"))
    assert missing.value.code == "PROVIDER_MISCONFIGURED"
