"""Retrieval over the chunked corpus.

Baseline implemented here: deterministic keyword retrieval with structure-aware
chunking. It needs no API key and no model, so it is fully unit-tested. The
semantic half of the intended hybrid design is the next layer; its open
decisions (embedding model, vector store, merge method) are listed in
DESIGN.md. Keyword-only is a defensible baseline for a small, well-structured
corpus and an honest starting point.
"""

from __future__ import annotations

import re
from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

_WORD = re.compile(r"[a-z0-9]+")
_HEADING = re.compile(r"^#{1,6}\s+(.*)$")

# Without these, any question sharing "the" or "what" with the corpus retrieves
# something, and refuse-when-ungrounded (DESIGN.md s5) never fires.
_STOPWORD_TEXT = (
    "a an and are as at be but by can do does for from has have how i if in is it "
    "its me my of on or our so that the their them then there they this to was we "
    "what when where which who why will with you your"
)
_STOPWORDS = frozenset(_STOPWORD_TEXT.split())


@dataclass(frozen=True)
class Chunk:
    """A retrievable unit. ``section`` travels with the text so a result is a
    citable unit (DESIGN.md: chunking)."""

    doc_id: str
    section: str
    text: str


@dataclass(frozen=True)
class Hit:
    chunk: Chunk
    score: float


def _tokens(text: str) -> list[str]:
    return [t for t in _WORD.findall(text.lower()) if t not in _STOPWORDS]


def chunk_document(doc_id: str, text: str) -> list[Chunk]:
    """Split a document into chunks on blank lines, tracking the most recent
    markdown heading as the section label. Structure-aware enough that each
    chunk carries where it came from."""
    chunks: list[Chunk] = []
    section = doc_id
    buf: list[str] = []

    def flush() -> None:
        body = "\n".join(buf).strip()
        if body:
            chunks.append(Chunk(doc_id=doc_id, section=section, text=body))
        buf.clear()

    for line in text.splitlines():
        heading = _HEADING.match(line.strip())
        if heading:
            flush()
            section = heading.group(1).strip()
            continue
        if not line.strip():
            flush()
            continue
        buf.append(line)
    flush()
    return chunks


class Retriever:
    """Keyword retriever. Scores a chunk by how many query-term occurrences it
    contains. Returns an empty list when nothing matches, which the agent must
    treat as a reason to refuse rather than invent (DESIGN.md s5)."""

    def __init__(self, chunks: Iterable[Chunk]) -> None:
        self._chunks = list(chunks)
        self._postings: dict[str, list[int]] = defaultdict(list)
        for i, chunk in enumerate(self._chunks):
            for tok in _tokens(chunk.text):
                self._postings[tok].append(i)

    @classmethod
    def from_corpus_dir(cls, corpus_dir: str | Path) -> Retriever:
        chunks: list[Chunk] = []
        for path in sorted(Path(corpus_dir).glob("**/*")):
            if path.suffix.lower() in {".md", ".txt"} and path.is_file():
                chunks.extend(
                    chunk_document(path.stem, path.read_text(encoding="utf-8"))
                )
        return cls(chunks)

    def search(self, query: str, k: int = 5) -> list[Hit]:
        scores: dict[int, float] = defaultdict(float)
        for tok in set(_tokens(query)):
            for idx in self._postings.get(tok, ()):
                scores[idx] += 1.0
        ranked = sorted(scores.items(), key=lambda kv: (-kv[1], kv[0]))
        return [Hit(chunk=self._chunks[i], score=s) for i, s in ranked[:k]]
