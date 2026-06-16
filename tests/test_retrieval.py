"""Deterministic tests for chunking and keyword retrieval. No network."""

from __future__ import annotations

from grounded.retrieval import Retriever, chunk_document


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
