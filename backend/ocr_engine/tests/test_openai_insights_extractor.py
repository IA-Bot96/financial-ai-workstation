"""Unit tests for the OpenAI insights extraction orchestrator."""

import logging
import sys
from pathlib import Path

import pytest

BACKEND_DIR = Path(__file__).resolve().parents[2]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from ocr_engine.exceptions.openai_exceptions import MissingOpenAIConfigurationError
from ocr_engine.models.insights_extraction import Insight, InsightsExtractionResult
from ocr_engine.models.table_normalization import NormalizationResult, NormalizedTable
from ocr_engine.services.chunk_builder import NarrativeChunk
from ocr_engine.services.narrative_text_extractor import NarrativePage
from ocr_engine.services.openai_insights_extractor import OpenAIInsightsExtractor
from ocr_engine.services.section_identifier import SectionPage


class FakeNarrativeTextExtractor:
    def extract(self, pdf_path: str) -> list[NarrativePage]:
        return [NarrativePage(page_number=84, text="Business Review\nExports grew.")]


class FakeSectionIdentifier:
    def identify_sections(self, pages: list[NarrativePage]) -> list[SectionPage]:
        return [
            SectionPage(
                page_number=84,
                section="Business Review",
                text=pages[0].text,
            )
        ]


class FakeChunkBuilder:
    def build_chunks(self, section_pages: list[SectionPage]) -> list[NarrativeChunk]:
        return [
            NarrativeChunk(
                page_number=84,
                source_section="Business Review",
                text="Exports grew due to Middle East expansion.",
            )
        ]


class FakeChunkRanker:
    def rank_chunks(
        self,
        chunks: list[NarrativeChunk],
        normalization_result: NormalizationResult,
    ) -> list[NarrativeChunk]:
        return chunks

    def extract_metric_context(
        self,
        normalization_result: NormalizationResult,
    ) -> tuple[str, ...]:
        return ("revenue",)


class FakePromptBuilder:
    def build_messages(
        self,
        chunks: list[NarrativeChunk],
        metric_context: tuple[str, ...],
    ) -> list[dict[str, str]]:
        return [{"role": "user", "content": chunks[0].text}]


class FakeInsightsExtractor:
    def __init__(self) -> None:
        self.messages: list[dict[str, str]] | None = None

    def extract(self, messages: list[dict[str, str]]) -> InsightsExtractionResult:
        self.messages = messages
        return InsightsExtractionResult(
            insights=[
                Insight(
                    area="Exports",
                    takeaway="Export sales increased due to Middle East expansion.",
                    source_section="Business Review",
                    page_number=84,
                    confidence=0.92,
                )
            ]
        )


def _normalization_result() -> NormalizationResult:
    return NormalizationResult(
        tables=[
            NormalizedTable(
                page_number=20,
                table_type="income_statement",
                table_index=0,
                rows=[["revenue", "1000"]],
            )
        ]
    )


def test_openai_insights_extractor_requires_api_key_without_injected_extractor() -> None:
    with pytest.raises(MissingOpenAIConfigurationError):
        OpenAIInsightsExtractor(api_key="DUMMY_KEY")


def test_openai_insights_extractor_orchestrates_preprocessing(
    caplog: pytest.LogCaptureFixture,
) -> None:
    fake_insights_extractor = FakeInsightsExtractor()
    extractor = OpenAIInsightsExtractor(
        insights_extractor=fake_insights_extractor,
        narrative_text_extractor=FakeNarrativeTextExtractor(),
        section_identifier=FakeSectionIdentifier(),
        chunk_builder=FakeChunkBuilder(),
        chunk_ranker=FakeChunkRanker(),
        prompt_builder=FakePromptBuilder(),
    )

    with caplog.at_level(logging.INFO):
        result = extractor.extract_insights(
            pdf_path="annual_report.pdf",
            normalization_result=_normalization_result(),
        )

    assert result.insights[0].area == "Exports"
    assert fake_insights_extractor.messages == [
        {
            "role": "user",
            "content": "Exports grew due to Middle East expansion.",
        }
    ]
    assert "Insights extraction complete" in caplog.text
