"""Narrative chunk construction for insights extraction."""

from __future__ import annotations

from dataclasses import dataclass
import re

from ocr_engine.constants.insights_constants import (
    INSIGHTS_CHUNK_MAX_CHARACTERS,
    INSIGHTS_CHUNK_OVERLAP_CHARACTERS,
)
from ocr_engine.services.section_identifier import SectionPage


@dataclass(frozen=True)
class NarrativeChunk:
    """A source-traceable text chunk passed to insight ranking and prompting."""

    page_number: int
    source_section: str
    text: str
    year: int | None = None
    score: float = 0.0


class ChunkBuilder:
    """Build source-traceable chunks from section-level narrative pages."""

    def __init__(
        self,
        max_characters: int = INSIGHTS_CHUNK_MAX_CHARACTERS,
        overlap_characters: int = INSIGHTS_CHUNK_OVERLAP_CHARACTERS,
    ) -> None:
        """Initialize chunk sizing rules."""

        if max_characters < 500:
            raise ValueError("max_characters must be at least 500.")
        if overlap_characters < 0:
            raise ValueError("overlap_characters cannot be negative.")

        self._max_characters = max_characters
        self._overlap_characters = overlap_characters

    def build_chunks(self, section_pages: list[SectionPage]) -> list[NarrativeChunk]:
        """Build chunks while preserving page and section traceability."""

        chunks: list[NarrativeChunk] = []
        for section_page in section_pages:
            clean_text = _clean_text(section_page.text)
            if not clean_text:
                continue

            chunks.extend(
                NarrativeChunk(
                    page_number=section_page.page_number,
                    source_section=section_page.section,
                    text=chunk,
                )
                for chunk in self._split_text(clean_text)
            )
        return chunks

    def _split_text(self, text: str) -> list[str]:
        """Split text into chunks using paragraph boundaries where possible."""

        if len(text) <= self._max_characters:
            return [text]

        paragraphs = [paragraph.strip() for paragraph in text.split("\n") if paragraph.strip()]
        chunks: list[str] = []
        current = ""

        for paragraph in paragraphs:
            if len(current) + len(paragraph) + 1 <= self._max_characters:
                current = f"{current}\n{paragraph}".strip()
                continue

            if current:
                chunks.append(current)
            current = paragraph

            while len(current) > self._max_characters:
                chunks.append(current[: self._max_characters].strip())
                start = max(0, self._max_characters - self._overlap_characters)
                current = current[start:].strip()

        if current:
            chunks.append(current)

        return chunks


def _clean_text(text: str) -> str:
    """Normalize whitespace without rewriting source language."""

    lines = [re.sub(r"\s+", " ", line).strip() for line in text.splitlines()]
    return "\n".join(line for line in lines if line)
