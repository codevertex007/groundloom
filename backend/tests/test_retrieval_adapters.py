import pytest
from app.ai.retrieval.providers.embeddings import (
    DeterministicEmbeddingProvider,
    OpenAICompatibleEmbeddingProvider,
    build_embedding_provider,
    cosine_similarity,
    hybrid_score,
)
from app.config import Settings
from app.errors import GroundloomError


def test_deterministic_embeddings_are_stable_bounded_and_dimension_safe():
    provider = DeterministicEmbeddingProvider(dimensions=16)
    first = provider.embed(["Torque guidance for service fasteners.", ""])
    second = provider.embed(["Torque guidance for service fasteners.", ""])
    assert first == second
    assert len(first) == 2 and all(len(vector) == 16 for vector in first)
    assert cosine_similarity(first[0], first[0]) == pytest.approx(1.0)
    assert 0.0 <= hybrid_score(0.8, 0.5) <= 1.0


def test_openai_compatible_provider_orders_and_validates_response(monkeypatch):
    calls = []

    class Embeddings:
        def embed_documents(self, texts):
            calls.append(texts)
            return [[1.0, 0.0], [0.0, 1.0]]

    provider = OpenAICompatibleEmbeddingProvider(
        api_key="secret-do-not-log",
        base_url="https://embeddings.example/v1",
        model="embedding-test",
        dimensions=2,
        client=Embeddings(),
    )
    vectors = provider.embed(["one", "two"])
    assert vectors == [[1.0, 0.0], [0.0, 1.0]]
    assert calls == [["one", "two"]]

    class BadEmbeddings:
        def embed_documents(self, _texts):
            return [[1.0, 0.0, 0.0]]

    bad_provider = OpenAICompatibleEmbeddingProvider(
        api_key="secret-do-not-log",
        base_url="https://embeddings.example/v1",
        model="embedding-test",
        dimensions=2,
        client=BadEmbeddings(),
    )
    with pytest.raises(GroundloomError) as invalid:
        bad_provider.embed(["one"])
    assert invalid.value.code == "PROVIDER_INVALID_RESPONSE"


def test_embedding_provider_outage_and_missing_configuration_are_typed():
    class UnavailableEmbeddings:
        def embed_documents(self, _texts):
            raise RuntimeError("provider credentials must not escape")

    provider = OpenAICompatibleEmbeddingProvider(
        api_key="secret-do-not-log",
        base_url="https://embeddings.example/v1",
        model="embedding-test",
        dimensions=2,
        client=UnavailableEmbeddings(),
    )
    with pytest.raises(GroundloomError) as outage:
        provider.embed(["one"])
    assert outage.value.code == "DEPENDENCY_UNAVAILABLE"
    assert outage.value.retryable is True
    assert "credentials" not in outage.value.message

    with pytest.raises(GroundloomError) as missing:
        build_embedding_provider(Settings(embedding_provider="openai"))
    assert missing.value.code == "PROVIDER_MISCONFIGURED"
