import httpx
import pytest
from app.config import Settings
from app.errors import GroundloomError
from app.reranking import (
    CohereCompatibleReranker,
    DeterministicReranker,
    build_reranker,
    combine_rerank_scores,
)


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

    class Response:
        status_code = 200

        def json(self):
            return {
                "results": [
                    {"index": 1, "relevance_score": 0.2},
                    {"index": 0, "relevance_score": 0.9},
                ]
            }

    def post(url, **kwargs):
        calls.append((url, kwargs))
        return Response()

    monkeypatch.setattr(httpx, "post", post)
    reranker = CohereCompatibleReranker(
        api_key="secret-do-not-log",
        base_url="https://rerank.example/v1",
        model="rerank-test",
    )
    assert reranker.score("query", ["first", "second"]) == [0.9, 0.2]
    assert calls[0][0] == "https://rerank.example/v1/rerank"
    assert calls[0][1]["json"]["documents"] == ["first", "second"]

    class BadResponse(Response):
        def json(self):
            return {"results": [{"index": 3, "relevance_score": 0.4}]}

    monkeypatch.setattr(httpx, "post", lambda *_args, **_kwargs: BadResponse())
    with pytest.raises(GroundloomError) as invalid:
        reranker.score("query", ["one"])
    assert invalid.value.code == "PROVIDER_INVALID_RESPONSE"


def test_reranker_outage_and_missing_configuration_are_typed(monkeypatch):
    monkeypatch.setattr(httpx, "post", lambda *_args, **_kwargs: (_ for _ in ()).throw(httpx.ConnectError("secret")))
    reranker = CohereCompatibleReranker(
        api_key="secret-do-not-log",
        base_url="https://rerank.example/v1",
        model="rerank-test",
    )
    with pytest.raises(GroundloomError) as outage:
        reranker.score("query", ["one"])
    assert outage.value.code == "DEPENDENCY_UNAVAILABLE"
    assert outage.value.retryable is True

    with pytest.raises(GroundloomError) as missing:
        build_reranker(Settings(reranker_provider="cohere"))
    assert missing.value.code == "PROVIDER_MISCONFIGURED"
