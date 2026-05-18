"""
Ranking helpers for merging retrieval result sets.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class RankedDocument:
    """Merged retrieval candidate for a document."""

    doc_id: str
    relative_path: str
    absolute_path: str
    position: int | None
    text: str
    semantic_score: float
    metadata_score: int

    @property
    def combined_score(self) -> float:
        # Semantic scores dominate ordering; metadata score boosts ties and
        # metadata-only matches into the candidate set.
        return float(self.semantic_score * 100 + self.metadata_score * 10)

    @property
    def matched_by(self) -> str:
        if self.semantic_score > 0 and self.metadata_score > 0:
            return "semantic+metadata"
        if self.semantic_score > 0:
            return "semantic"
        return "metadata"


def rank_documents(
    documents: list[RankedDocument], *, limit: int
) -> list[RankedDocument]:
    """Sort merged retrieval results and apply limit."""
    ordered = sorted(
        documents,
        key=lambda doc: (
            -doc.combined_score,
            -doc.semantic_score,
            -doc.metadata_score,
            doc.position if doc.position is not None else 10**9,
            doc.relative_path,
        ),
    )
    return ordered[: max(limit, 1)]
