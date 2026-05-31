"""Unit tests for narrative chunk ranking."""

import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[2]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from ocr_engine.models.table_normalization import NormalizationResult, NormalizedTable
from ocr_engine.services.chunk_builder import NarrativeChunk
from ocr_engine.services.chunk_ranker import ChunkRanker


def _normalization_result() -> NormalizationResult:
    return NormalizationResult(
        tables=[
            NormalizedTable(
                year=2024,
                page_number=20,
                table_type="income_statement",
                table_index=0,
                rows=[["revenue", "1200"], ["finance_cost", "80"]],
            )
        ]
    )


def test_chunk_ranker_uses_keywords_metrics_and_section_importance() -> None:
    ranker = ChunkRanker(max_chunks=1)
    chunks = [
        NarrativeChunk(
            page_number=1,
            source_section="Chairman Review",
            text="The company had a stable year.",
        ),
        NarrativeChunk(
            page_number=2,
            source_section="Management Discussion & Analysis",
            text="Debt and finance cost increased due to capacity expansion.",
        ),
    ]

    ranked = ranker.rank_chunks(chunks, _normalization_result())

    assert len(ranked) == 1
    assert ranked[0].page_number == 2
    assert ranked[0].score > 0


def test_chunk_ranker_extracts_metric_context_with_pandas() -> None:
    metrics = ChunkRanker().extract_metric_context(_normalization_result())

    assert metrics == ("revenue", "finance_cost")


def test_chunk_ranker_uses_all_relevant_chunks_with_section_balance() -> None:
    ranker = ChunkRanker()
    chunks = [
        NarrativeChunk(
            page_number=index,
            source_section="Business Review",
            text="Expansion and debt increased.",
        )
        for index in range(1, 14)
    ] + [
        NarrativeChunk(
            page_number=50 + index,
            source_section="Risks",
            text="Cost and working capital risks increased.",
        )
        for index in range(1, 4)
    ]

    ranked = ranker.rank_chunks(chunks, _normalization_result())

    assert len(ranked) == 16
    assert ranked[0].source_section == "Business Review"
    assert ranked[1].source_section == "Risks"
    assert {chunk.source_section for chunk in ranked} == {
        "Business Review",
        "Risks",
    }
