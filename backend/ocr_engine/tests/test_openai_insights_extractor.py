"""Unit tests for the OpenAI insights extraction orchestrator."""

import logging
import re
import sys
from pathlib import Path

import pytest

BACKEND_DIR = Path(__file__).resolve().parents[2]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from ocr_engine.exceptions.openai_exceptions import MissingOpenAIConfigurationError
from ocr_engine.models.insights_extraction import Insight, InsightsExtractionResult
from ocr_engine.models.table_normalization import (
    MetricMapping,
    NormalizationResult,
    NormalizedTable,
)
from ocr_engine.pipeline.exceptions import PipelineLayerPartialFailure
from ocr_engine.services.chunk_builder import NarrativeChunk
from ocr_engine.services.narrative_text_extractor import NarrativePage
from ocr_engine.services.openai_insights_extractor import OpenAIInsightsExtractor
from ocr_engine.services.section_identifier import SectionPage
from shared.models.company_context import CompanyContext
from shared.models.report import Report


class FakeNarrativeTextExtractor:
    def __init__(self) -> None:
        self.pdf_paths: list[str] = []

    def extract(self, pdf_path: str) -> list[NarrativePage]:
        self.pdf_paths.append(pdf_path)
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
        report_year: int,
    ) -> list[dict[str, str]]:
        return [
            {
                "role": "user",
                "content": f"year: {report_year}\n{chunks[0].text}",
            }
        ]


class FakeInsightsExtractor:
    def __init__(self) -> None:
        self.messages_by_call: list[list[dict[str, str]]] = []

    def extract(self, messages: list[dict[str, str]]) -> InsightsExtractionResult:
        self.messages_by_call.append(messages)
        content = messages[0]["content"]
        year = 2023 if "year: 2023" in content else 2024
        return InsightsExtractionResult(
            insights=[
                Insight(
                    value_year=year,
                    source_report_year=year,
                    area="Debt",
                    takeaway="Borrowings increased to finance expansion.",
                    source_section="Business Review",
                    page_number=84,
                    confidence=0.92,
                )
            ]
        )


class FakeOpenAIResponse:
    def __init__(self, output_text: str) -> None:
        self.output_text = output_text


class FakeOpenAIResponsesClient:
    def __init__(self, responses: list[object]) -> None:
        self._responses = responses
        self.calls: list[dict[str, object]] = []

    def create(self, **kwargs: object) -> object:
        self.calls.append(kwargs)
        response = self._responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response


class FakeOpenAIClient:
    def __init__(self, responses: list[object]) -> None:
        self.responses = FakeOpenAIResponsesClient(responses)


def _normalization_result(year: int = 2024) -> NormalizationResult:
    return NormalizationResult(
        tables=[
            NormalizedTable(
                year=year,
                page_number=20,
                table_type="income_statement",
                table_index=0,
                rows=[["revenue", "1000"]],
            )
        ]
    )


def test_openai_insights_extractor_requires_api_key_without_injected_extractor(
) -> None:
    with pytest.raises(MissingOpenAIConfigurationError):
        OpenAIInsightsExtractor(api_key="")


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

    assert result.insights[0].area == "Debt"
    assert result.insights[0].value_year == 2024
    assert result.insights[0].source_report_year == 2024
    assert fake_insights_extractor.messages_by_call == [
        [
            {
                "role": "user",
                "content": (
                    "year: 2024\n"
                    "Exports grew due to Middle East expansion."
                ),
            }
        ]
    ]
    assert "Insights extraction complete" in caplog.text


def test_openai_insights_extractor_passes_request_timeout() -> None:
    client = FakeOpenAIClient([FakeOpenAIResponse('{"insights": []}')])
    extractor = OpenAIInsightsExtractor(
        client=client,
        api_key="test_key",
        request_timeout_seconds=17.0,
        max_retries=1,
        retry_backoff_seconds=0,
        narrative_text_extractor=FakeNarrativeTextExtractor(),
        section_identifier=FakeSectionIdentifier(),
        chunk_builder=FakeChunkBuilder(),
        chunk_ranker=FakeChunkRanker(),
        prompt_builder=FakePromptBuilder(),
    )

    extractor.extract_insights(
        pdf_path="annual_report.pdf",
        normalization_result=_normalization_result(),
    )

    assert client.responses.calls[0]["timeout"] == 17.0


def test_extract_insights_for_context_stores_results_by_report_year() -> None:
    fake_insights_extractor = FakeInsightsExtractor()
    fake_narrative_extractor = FakeNarrativeTextExtractor()
    extractor = OpenAIInsightsExtractor(
        insights_extractor=fake_insights_extractor,
        narrative_text_extractor=fake_narrative_extractor,
        section_identifier=FakeSectionIdentifier(),
        chunk_builder=FakeChunkBuilder(),
        chunk_ranker=FakeChunkRanker(),
        prompt_builder=FakePromptBuilder(),
    )
    context = CompanyContext(
        company_name="Maple Leaf Cement Factory Limited",
        reports=[
            Report(
                id="rpt_2023_001",
                company_name="Maple Leaf Cement Factory Limited",
                year=2023,
                file_name="MLCF_2023_Annual_Report.pdf",
                file_path="reports/MLCF_2023.pdf",
            ),
            Report(
                id="rpt_2024_001",
                company_name="Maple Leaf Cement Factory Limited",
                year=2024,
                file_name="MLCF_2024_Annual_Report.pdf",
                file_path="reports/MLCF_2024.pdf",
            ),
        ],
        normalization_results={
            2023: _normalization_result(year=2023),
            2024: _normalization_result(year=2024),
        },
    )

    updated_context = extractor.extract_insights_for_context(context)

    assert updated_context is context
    assert set(context.insights_results) == {2023, 2024}
    assert context.insights_results[2023].model_dump(
        exclude={"diagnostics"}
    ) == {
        "insights": [
            {
                "value_year": 2023,
                "source_report_year": 2023,
                "area": "Debt",
                "takeaway": "Borrowings increased to finance expansion.",
                "source_section": "Business Review",
                "page_number": 84,
                "confidence": 0.92,
            }
        ]
    }
    assert context.insights_results[2024].model_dump(
        exclude={"diagnostics"}
    ) == {
        "insights": [
            {
                "value_year": 2024,
                "source_report_year": 2024,
                "area": "Debt",
                "takeaway": "Borrowings increased to finance expansion.",
                "source_section": "Business Review",
                "page_number": 84,
                "confidence": 0.92,
            }
        ]
    }
    assert context.insights_results[2023] is not context.insights_results[2024]
    assert fake_narrative_extractor.pdf_paths == [
        "reports/MLCF_2023.pdf",
        "reports/MLCF_2024.pdf",
    ]
    assert len(fake_insights_extractor.messages_by_call) == 2


def test_extract_insights_for_context_requires_normalization_result_per_year() -> None:
    extractor = OpenAIInsightsExtractor(
        insights_extractor=FakeInsightsExtractor(),
        narrative_text_extractor=FakeNarrativeTextExtractor(),
        section_identifier=FakeSectionIdentifier(),
        chunk_builder=FakeChunkBuilder(),
        chunk_ranker=FakeChunkRanker(),
        prompt_builder=FakePromptBuilder(),
    )
    context = CompanyContext(
        company_name="Maple Leaf Cement Factory Limited",
        reports=[
            Report(
                id="rpt_2024_001",
                company_name="Maple Leaf Cement Factory Limited",
                year=2024,
                file_name="MLCF_2024_Annual_Report.pdf",
                file_path="reports/MLCF_2024.pdf",
            )
        ],
    )

    with pytest.raises(
        PipelineLayerPartialFailure,
        match="Missing normalization result",
    ) as exc_info:
        extractor.extract_insights_for_context(context)

    assert context.insights_results[2024].model_dump(
        exclude={"diagnostics"}
    ) == {"insights": []}
    assert context.pipeline_errors == []
    assert "Report year 2024 failed insights extraction" in (
        exc_info.value.error_messages[0]
    )


def test_extract_insights_for_context_rejects_contaminated_year_bucket() -> None:
    extractor = OpenAIInsightsExtractor(
        insights_extractor=FakeInsightsExtractor(),
        narrative_text_extractor=FakeNarrativeTextExtractor(),
        section_identifier=FakeSectionIdentifier(),
        chunk_builder=FakeChunkBuilder(),
        chunk_ranker=FakeChunkRanker(),
        prompt_builder=FakePromptBuilder(),
    )
    context = CompanyContext(
        company_name="Maple Leaf Cement Factory Limited",
        reports=[
            Report(
                id="rpt_2024_001",
                company_name="Maple Leaf Cement Factory Limited",
                year=2024,
                file_name="MLCF_2024_Annual_Report.pdf",
                file_path="reports/MLCF_2024.pdf",
            )
        ],
        normalization_results={2024: _normalization_result(year=2023)},
    )

    with pytest.raises(
        PipelineLayerPartialFailure,
        match="contains data from other years",
    ) as exc_info:
        extractor.extract_insights_for_context(context)

    assert context.insights_results[2024].insights == []
    assert context.pipeline_errors == []
    assert "Report year 2024 failed insights extraction" in (
        exc_info.value.error_messages[0]
    )


def test_extract_insights_rejects_merged_multi_year_normalization() -> None:
    extractor = OpenAIInsightsExtractor(
        insights_extractor=FakeInsightsExtractor(),
        narrative_text_extractor=FakeNarrativeTextExtractor(),
        section_identifier=FakeSectionIdentifier(),
        chunk_builder=FakeChunkBuilder(),
        chunk_ranker=FakeChunkRanker(),
        prompt_builder=FakePromptBuilder(),
    )

    with pytest.raises(ValueError, match="single report year"):
        extractor.extract_insights(
            pdf_path="annual_report.pdf",
            normalization_result=NormalizationResult(
                tables=[
                    _normalization_result(year=2023).tables[0],
                    _normalization_result(year=2024).tables[0],
                ]
            ),
        )


def test_extract_insights_preserves_year_from_mapping_when_tables_are_empty() -> None:
    fake_insights_extractor = FakeInsightsExtractor()
    extractor = OpenAIInsightsExtractor(
        insights_extractor=fake_insights_extractor,
        narrative_text_extractor=FakeNarrativeTextExtractor(),
        section_identifier=FakeSectionIdentifier(),
        chunk_builder=FakeChunkBuilder(),
        chunk_ranker=FakeChunkRanker(),
        prompt_builder=FakePromptBuilder(),
    )

    result = extractor.extract_insights(
        pdf_path="annual_report.pdf",
        normalization_result=NormalizationResult(
            tables=[],
            mappings=[
                MetricMapping(
                    value_year=2024,
                    source_report_year=2024,
                    original_metric="Net Sales",
                    normalized_metric="revenue",
                    confidence=0.96,
                    requires_review=False,
                )
            ],
        ),
    )

    assert result.insights[0].source_report_year == 2024
    assert fake_insights_extractor.messages_by_call == [
        [
            {
                "role": "user",
                "content": (
                    "year: 2024\n"
                    "Exports grew due to Middle East expansion."
                ),
            }
        ]
    ]


def test_extract_insights_corrects_llm_year_to_report_year() -> None:
    class WrongYearInsightsExtractor:
        def extract(self, messages: list[dict[str, str]]) -> InsightsExtractionResult:
            return InsightsExtractionResult(
                insights=[
                    Insight(
                        value_year=2024,
                        source_report_year=2022,
                        area="Debt",
                        takeaway="Borrowings increased to finance expansion.",
                        source_section="Business Review",
                        page_number=84,
                        confidence=0.92,
                    )
                ]
            )

    extractor = OpenAIInsightsExtractor(
        insights_extractor=WrongYearInsightsExtractor(),
        narrative_text_extractor=FakeNarrativeTextExtractor(),
        section_identifier=FakeSectionIdentifier(),
        chunk_builder=FakeChunkBuilder(),
        chunk_ranker=FakeChunkRanker(),
        prompt_builder=FakePromptBuilder(),
    )

    result = extractor.extract_insights(
        pdf_path="annual_report.pdf",
        normalization_result=_normalization_result(year=2024),
    )

    assert result.insights[0].source_report_year == 2024


def test_extract_insights_deduplicates_after_year_normalization() -> None:
    class DuplicateYearInsightsExtractor:
        def extract(self, messages: list[dict[str, str]]) -> InsightsExtractionResult:
            return InsightsExtractionResult(
                insights=[
                    Insight(
                        value_year=2024,
                        source_report_year=2023,
                        area="Debt",
                        takeaway="Borrowings increased to finance expansion.",
                        source_section="Business Review",
                        page_number=84,
                        confidence=0.92,
                    ),
                    Insight(
                        value_year=2024,
                        source_report_year=2024,
                        area="Debt",
                        takeaway="Borrowings increased to finance expansion.",
                        source_section="Business Review",
                        page_number=84,
                        confidence=0.9,
                    ),
                ]
            )

    extractor = OpenAIInsightsExtractor(
        insights_extractor=DuplicateYearInsightsExtractor(),
        narrative_text_extractor=FakeNarrativeTextExtractor(),
        section_identifier=FakeSectionIdentifier(),
        chunk_builder=FakeChunkBuilder(),
        chunk_ranker=FakeChunkRanker(),
        prompt_builder=FakePromptBuilder(),
    )

    result = extractor.extract_insights(
        pdf_path="annual_report.pdf",
        normalization_result=_normalization_result(year=2024),
    )

    assert len(result.insights) == 1
    assert result.insights[0].source_report_year == 2024


def test_extract_insights_rejects_invalid_ranked_chunk_references() -> None:
    class InvalidReferenceInsightsExtractor:
        def extract(self, messages: list[dict[str, str]]) -> InsightsExtractionResult:
            return InsightsExtractionResult(
                insights=[
                    Insight(
                        value_year=2024,
                        source_report_year=2024,
                        area="Exports",
                        takeaway="Exports grew due to Middle East expansion.",
                        source_section="Business Review",
                        page_number=84,
                        confidence=0.92,
                    ),
                    Insight(
                        value_year=2024,
                        source_report_year=2024,
                        area="Debt",
                        takeaway="Borrowings increased.",
                        source_section="Business Review",
                        page_number=999,
                        confidence=0.9,
                    ),
                    Insight(
                        value_year=2024,
                        source_report_year=2024,
                        area="Margins",
                        takeaway="Margins improved.",
                        source_section="Chairman Review",
                        page_number=84,
                        confidence=0.9,
                    ),
                ]
            )

    extractor = OpenAIInsightsExtractor(
        insights_extractor=InvalidReferenceInsightsExtractor(),
        narrative_text_extractor=FakeNarrativeTextExtractor(),
        section_identifier=FakeSectionIdentifier(),
        chunk_builder=FakeChunkBuilder(),
        chunk_ranker=FakeChunkRanker(),
        prompt_builder=FakePromptBuilder(),
    )

    result = extractor.extract_insights(
        pdf_path="annual_report.pdf",
        normalization_result=_normalization_result(year=2024),
    )

    assert [insight.area for insight in result.insights] == ["Exports"]


def test_extract_insights_returns_empty_when_no_relevant_chunks() -> None:
    class EmptyChunkRanker(FakeChunkRanker):
        def rank_chunks(
            self,
            chunks: list[NarrativeChunk],
            normalization_result: NormalizationResult,
        ) -> list[NarrativeChunk]:
            return []

    extractor = OpenAIInsightsExtractor(
        insights_extractor=FakeInsightsExtractor(),
        narrative_text_extractor=FakeNarrativeTextExtractor(),
        section_identifier=FakeSectionIdentifier(),
        chunk_builder=FakeChunkBuilder(),
        chunk_ranker=EmptyChunkRanker(),
        prompt_builder=FakePromptBuilder(),
    )

    result = extractor.extract_insights(
        pdf_path="annual_report.pdf",
        normalization_result=_normalization_result(year=2024),
    )

    assert result.insights == []
    assert result.diagnostics.total_chunks_created == 1
    assert result.diagnostics.chunks_sent_to_llm == 0


def test_extract_insights_batches_all_ranked_chunks_and_records_diagnostics() -> None:
    class MultiPageNarrativeTextExtractor:
        last_total_pages_processed = 5

        def extract(self, pdf_path: str) -> list[NarrativePage]:
            return [
                NarrativePage(page_number=page_number, text=f"Page {page_number}")
                for page_number in range(1, 6)
            ]

    class MultiSectionIdentifier:
        def identify_sections(self, pages: list[NarrativePage]) -> list[SectionPage]:
            sections = [
                "Business Review",
                "Business Review",
                "Risks",
                "Outlook",
                "Outlook",
            ]
            return [
                SectionPage(
                    page_number=page.page_number,
                    section=sections[index],
                    text=f"{sections[index]}\nExpansion and debt text {page.page_number}.",
                )
                for index, page in enumerate(pages)
            ]

    class MultiChunkBuilder:
        max_characters = 2800
        overlap_characters = 250

        def build_chunks(
            self,
            section_pages: list[SectionPage],
        ) -> list[NarrativeChunk]:
            return [
                NarrativeChunk(
                    page_number=section_page.page_number,
                    source_section=section_page.section,
                    text=section_page.text,
                    score=10,
                )
                for section_page in section_pages
            ]

    class MultiChunkRanker(FakeChunkRanker):
        max_chunks = None
        retrieval_strategy = "section_balanced_score_all_relevant_chunks"

    class BatchAwareInsightsExtractor:
        def __init__(self) -> None:
            self.messages_by_call: list[list[dict[str, str]]] = []

        def extract(self, messages: list[dict[str, str]]) -> InsightsExtractionResult:
            self.messages_by_call.append(messages)
            content = messages[1]["content"]
            insights = []
            for section, page_number in re.findall(
                r"source_section: (.+?)\npage_number: (\d+)",
                content,
            ):
                insights.append(
                    Insight(
                        value_year=2024,
                        source_report_year=2024,
                        area=f"{section} {page_number}",
                        takeaway=f"{section} insight from page {page_number}.",
                        source_section=section,
                        page_number=int(page_number),
                        confidence=0.9,
                    )
                )
            return InsightsExtractionResult(insights=insights)

    fake_insights_extractor = BatchAwareInsightsExtractor()
    extractor = OpenAIInsightsExtractor(
        insights_extractor=fake_insights_extractor,
        narrative_text_extractor=MultiPageNarrativeTextExtractor(),
        section_identifier=MultiSectionIdentifier(),
        chunk_builder=MultiChunkBuilder(),
        chunk_ranker=MultiChunkRanker(),
        chunks_per_llm_call=2,
    )

    result = extractor.extract_insights(
        pdf_path="annual_report.pdf",
        normalization_result=_normalization_result(year=2024),
    )

    assert len(fake_insights_extractor.messages_by_call) == 3
    assert len(result.insights) == 5
    assert result.diagnostics.total_pages_processed == 5
    assert result.diagnostics.total_chunks_created == 5
    assert result.diagnostics.chunks_sent_to_llm == 5
    assert result.diagnostics.llm_call_count == 3
    assert result.diagnostics.generated_insights == 5
    assert result.diagnostics.insight_count_by_section == {
        "Business Review": 2,
        "Outlook": 2,
        "Risks": 1,
    }


def test_openai_insights_extractor_old_message_shape_removed() -> None:
    fake_insights_extractor = FakeInsightsExtractor()

    OpenAIInsightsExtractor(
        insights_extractor=fake_insights_extractor,
        narrative_text_extractor=FakeNarrativeTextExtractor(),
        section_identifier=FakeSectionIdentifier(),
        chunk_builder=FakeChunkBuilder(),
        chunk_ranker=FakeChunkRanker(),
        prompt_builder=FakePromptBuilder(),
    ).extract_insights(
        pdf_path="annual_report.pdf",
        normalization_result=_normalization_result(),
    )

    assert fake_insights_extractor.messages_by_call[0] == [
        {
            "role": "user",
            "content": "year: 2024\nExports grew due to Middle East expansion.",
        }
    ]
