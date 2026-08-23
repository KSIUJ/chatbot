"""
Testy encoder.py. Nie pobieramy realnego modelu (siec/GPU) - podmieniamy
sentence_transformers.SentenceTransformer na fake'a i sprawdzamy tylko logike
Encodera: dobor modelu/prefiksow oraz stosowanie prefiksow query/passage.
"""

import sys
import types

import pytest


class _FakeSentenceTransformer:
    """Podmiana SentenceTransformer - zapamietuje, co dostala do zakodowania."""

    last_instance = None

    def __init__(self, model_name, device=None):
        self.model_name = model_name
        self.device = device
        self.encoded_texts = []
        _FakeSentenceTransformer.last_instance = self

    def encode(self, texts, convert_to_numpy=True, normalize_embeddings=True):
        import numpy as np

        if isinstance(texts, str):
            self.encoded_texts.append(texts)
            return np.array([1.0, 0.0])

        self.encoded_texts.append(list(texts))
        return np.array([[1.0, 0.0] for _ in texts])


@pytest.fixture
def fake_sentence_transformers(monkeypatch):
    fake_module = types.ModuleType("sentence_transformers")
    fake_module.SentenceTransformer = _FakeSentenceTransformer
    monkeypatch.setitem(sys.modules, "sentence_transformers", fake_module)
    return fake_module


def _import_encoder():
    from RAG.encoder import Encoder

    return Encoder


def test_default_model_and_prefixes(fake_sentence_transformers, monkeypatch):
    monkeypatch.delenv("RAG_EMBEDDING_MODEL", raising=False)
    monkeypatch.delenv("RAG_QUERY_PREFIX", raising=False)
    monkeypatch.delenv("RAG_PASSAGE_PREFIX", raising=False)

    Encoder = _import_encoder()
    encoder = Encoder()

    assert encoder.model_name == "sdadas/mmlw-roberta-large"
    assert encoder.query_prefix == "zapytanie: "
    assert encoder.passage_prefix == ""


def test_model_name_overridable_via_env(fake_sentence_transformers, monkeypatch):
    monkeypatch.setenv("RAG_EMBEDDING_MODEL", "intfloat/multilingual-e5-large")

    Encoder = _import_encoder()
    encoder = Encoder()

    assert encoder.model_name == "intfloat/multilingual-e5-large"


def test_embed_query_applies_query_prefix(fake_sentence_transformers):
    Encoder = _import_encoder()
    encoder = Encoder(query_prefix="zapytanie: ", passage_prefix="")

    encoder.embed_query("gdzie jest dziekanat")

    fake = _FakeSentenceTransformer.last_instance
    assert fake.encoded_texts[-1] == "zapytanie: gdzie jest dziekanat"


def test_embed_batch_applies_passage_prefix(fake_sentence_transformers):
    Encoder = _import_encoder()
    encoder = Encoder(query_prefix="zapytanie: ", passage_prefix="fragment: ")

    encoder.embed_batch(["tekst A", "tekst B"])

    fake = _FakeSentenceTransformer.last_instance
    assert fake.encoded_texts[-1] == ["fragment: tekst A", "fragment: tekst B"]
