"""Rule-based ranking for narrative insight chunks."""

from __future__ import annotations

from collections import defaultdict
import re

import pandas as pd

from ocr_engine.constants.insights_constants import (
    INSIGHTS_FINANCIAL_KEYWORDS,
    INSIGHTS_MAX_RANKED_CHUNKS,
    INSIGHTS_RELEVANT_SECTIONS,
    INSIGHTS_RETRIEVAL_STRATEGY,
)
from ocr_engine.models.table_normalization import NormalizationResult
from ocr_engine.services.chunk_builder import NarrativeChunk


class ChunkRanker:
    """Rank chunks by financial keywords, canonical metric context, and section value."""

    _section_weights = {
        "Management Discussion & Analysis": 5.0,
        "Business Review": 4.5,
        "Directors Report": 4.0,
        "CEO Review": 3.5,
        "Chairman Review": 3.0,
        "Outlook": 3.0,
        "Risks": 2.5,
        "Opportunities": 2.5,
    }

    def __init__(
        self,
        financial_keywords: tuple[str, ...] = INSIGHTS_FINANCIAL_KEYWORDS,
        max_chunks: int | None = INSIGHTS_MAX_RANKED_CHUNKS,
    ) -> None:
        """Initialize ranking configuration."""

        if max_chunks is not None and max_chunks < 1:
            raise ValueError("max_chunks must be at least 1.")

        self._financial_keywords = tuple(keyword.lower() for keyword in financial_keywords)
        self._max_chunks = max_chunks
        self._retrieval_strategy = INSIGHTS_RETRIEVAL_STRATEGY

    @property
    def max_chunks(self) -> int | None:
        """Return the optional top-k ranked chunk limit."""

        return self._max_chunks

    @property
    def retrieval_strategy(self) -> str:
        """Return the retrieval strategy used to order narrative chunks."""

        return self._retrieval_strategy

    def rank_chunks(
        self,
        chunks: list[NarrativeChunk],
        normalization_result: NormalizationResult,
    ) -> list[NarrativeChunk]:
        """Return the highest-signal chunks for OpenAI analysis."""

        metric_context = self.extract_metric_context(normalization_result)
        ranked_chunks = [
            NarrativeChunk(
                page_number=chunk.page_number,
                source_section=chunk.source_section,
                text=chunk.text,
                year=chunk.year,
                score=self._score_chunk(chunk, metric_context),
            )
            for chunk in chunks
        ]
        relevant_chunks = [chunk for chunk in ranked_chunks if chunk.score > 0]
        ordered_chunks = self._section_balanced_order(relevant_chunks)
        if self._max_chunks is None:
            return ordered_chunks
        return ordered_chunks[: self._max_chunks]

    def extract_metric_context(
        self,
        normalization_result: NormalizationResult,
    ) -> tuple[str, ...]:
        """Extract canonical metric labels from normalized tables using pandas."""

        metrics: list[str] = []
        seen: set[str] = set()

        for table in normalization_result.tables:
            dataframe = pd.DataFrame(table.rows)
            for _, row in dataframe.iterrows():
                cells = ["" if value is None else str(value).strip() for value in row.tolist()]
                label = self._first_text_cell(cells)
                if label is None:
                    continue

                normalized_label = _normalize_metric_label(label)
                if normalized_label and normalized_label not in seen:
                    metrics.append(normalized_label)
                    seen.add(normalized_label)

        return tuple(metrics)

    def _score_chunk(
        self,
        chunk: NarrativeChunk,
        metric_context: tuple[str, ...],
    ) -> float:
        text = chunk.text.lower()
        score = self._section_weights.get(chunk.source_section, 1.0)

        for keyword in self._financial_keywords:
            if keyword in text:
                score += 2.0

        for metric in metric_context:
            metric_text = metric.replace("_", " ")
            if metric_text in text or metric in text:
                score += 1.5

        return score

    @staticmethod
    def _first_text_cell(cells: list[str]) -> str | None:
        """Return the first non-empty text-like cell from a normalized table row."""

        for cell in cells:
            if cell and re.search(r"[A-Za-z]", cell):
                return cell
        return None

    @staticmethod
    def _section_balanced_order(
        chunks: list[NarrativeChunk],
    ) -> list[NarrativeChunk]:
        """Order chunks by score while preserving coverage across sections."""

        chunks_by_section: dict[str, list[NarrativeChunk]] = defaultdict(list)
        for chunk in chunks:
            chunks_by_section[chunk.source_section].append(chunk)

        for section_chunks in chunks_by_section.values():
            section_chunks.sort(key=lambda chunk: chunk.score, reverse=True)

        section_order = [
            section
            for section in INSIGHTS_RELEVANT_SECTIONS
            if section in chunks_by_section
        ]
        section_order.extend(
            sorted(
                section
                for section in chunks_by_section
                if section not in section_order
            )
        )

        ordered: list[NarrativeChunk] = []
        while any(chunks_by_section[section] for section in section_order):
            for section in section_order:
                if chunks_by_section[section]:
                    ordered.append(chunks_by_section[section].pop(0))
        return ordered


def _normalize_metric_label(value: str) -> str:
    """Normalize a table row label into canonical metric key style."""

    normalized = value.lower().replace("&", " and ")
    normalized = re.sub(r"[^a-z0-9_]+", " ", normalized)
    normalized = re.sub(r"\s+", "_", normalized)
    return normalized.strip("_")
