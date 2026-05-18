"""
Chunking utilities for indexing document content.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class TextChunk:
    """A content chunk with source offsets."""

    text: str
    position: int
    start_char: int
    end_char: int


class SmartChunker:
    """
    Paragraph-aware chunker with overlap.

    This implementation is char-based to keep it deterministic and lightweight.
    """

    def __init__(self, chunk_size: int = 1500, overlap: int = 150) -> None:
        if chunk_size <= 0:
            raise ValueError("chunk_size must be > 0")
        if overlap < 0:
            raise ValueError("overlap must be >= 0")
        if overlap >= chunk_size:
            raise ValueError("overlap must be smaller than chunk_size")

        self.chunk_size = chunk_size
        self.overlap = overlap

    def chunk_text(self, text: str) -> list[TextChunk]:
        """
        Split text into chunks while preferring paragraph boundaries.
        """
        normalized = text.strip()
        if not normalized:
            return []

        chunks: list[TextChunk] = []
        start = 0
        position = 0
        total = len(normalized)

        while start < total:
            tentative_end = min(start + self.chunk_size, total)
            end = tentative_end

            if tentative_end < total:
                boundary = normalized.rfind("\n\n", start + (self.chunk_size // 2), tentative_end)
                if boundary != -1:
                    end = boundary + 2

            chunk_text = normalized[start:end].strip()
            if chunk_text:
                chunks.append(
                    TextChunk(
                        text=chunk_text,
                        position=position,
                        start_char=start,
                        end_char=end,
                    )
                )
                position += 1

            if end >= total:
                break
            start = max(0, end - self.overlap)

        return chunks
