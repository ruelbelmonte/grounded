"""Deterministic tests for chunking and keyword retrieval. No network."""

from __future__ import annotations

from pathlib import Path

import pytest

from grounded.retrieval import Retriever, chunk_document

_SAMPLE_CORPUS = Path(__file__).resolve().parents[1] / "sample_corpus"


def test_chunking_tracks_headings_as_sections() -> None:
    doc = "# Access\n\nYou may request your information.\n\n# Refusal\n\nAccess may be refused."
    chunks = chunk_document("policy", doc)
    sections = {c.section for c in chunks}
    assert sections == {"Access", "Refusal"}
    assert any("request your information" in c.text for c in chunks)


def test_search_ranks_relevant_chunk_first() -> None:
    chunks = chunk_document(
        "policy",
        "# Retention\n\nDelete records when no longer needed.\n\n"
        "# Access\n\nA person may request access to their personal information.",
    )
    r = Retriever(chunks)
    hits = r.search("how do I request access to my information?")
    assert hits
    assert hits[0].chunk.section == "Access"


def test_search_returns_empty_when_nothing_matches() -> None:
    r = Retriever(chunk_document("policy", "# A\n\napples and oranges"))
    assert r.search("quantum chromodynamics") == []


@pytest.mark.parametrize(
    "question",
    [
        "What is the capital of France?",
        "What should I eat for dinner?",
        "What is the maximum fine under this policy?",
        "Is OWASP covered?",
    ],
)
def test_off_topic_questions_retrieve_nothing_from_sample_corpus(
    question: str,
) -> None:
    r = Retriever.from_corpus_dir(_SAMPLE_CORPUS)
    assert r.search(question) == []


def test_html_comments_are_not_indexed() -> None:
    doc = "<!--\nDisclaimer: mentions OWASP.\n-->\n# Access\n\nRequest access."
    chunks = chunk_document("policy", doc)
    assert all("OWASP" not in c.text for c in chunks)
    assert Retriever(chunks).search("OWASP") == []
