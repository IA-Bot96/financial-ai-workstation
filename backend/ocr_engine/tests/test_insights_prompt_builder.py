"""Unit tests for insights prompt construction."""

import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[2]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from ocr_engine.services.chunk_builder import NarrativeChunk
from ocr_engine.services.prompt_builders.insights_prompt_builder import (
    InsightsPromptBuilder,
)


def test_insights_prompt_builder_includes_source_and_metric_context() -> None:
    messages = InsightsPromptBuilder().build_messages(
        chunks=[
            NarrativeChunk(
                page_number=84,
                source_section="Management Discussion & Analysis",
                text="Borrowings increased to finance expansion.",
                score=10,
            )
        ],
        metric_context=("revenue", "finance_cost"),
        report_year=2024,
    )

    assert messages[0]["role"] == "system"
    assert "JSON only" in messages[0]["content"]
    assert "page_number: 84" in messages[1]["content"]
    assert "year: 2024" in messages[1]["content"]
    assert "finance_cost" in messages[1]["content"]
