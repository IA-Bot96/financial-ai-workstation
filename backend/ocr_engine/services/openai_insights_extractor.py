"""OpenAI-backed OCR insights extraction service."""

from __future__ import annotations

from collections import Counter
import logging
from typing import Any

from ocr_engine.constants.ai_constants import (
    OPENAI_API_KEY,
    OPENAI_INSIGHTS_MAX_RETRIES,
    OPENAI_INSIGHTS_REQUEST_TIMEOUT_SECONDS,
    OPENAI_INSIGHTS_RETRY_BACKOFF_SECONDS,
    OPENAI_MODEL,
)
from ocr_engine.constants.insights_constants import INSIGHTS_CHUNKS_PER_LLM_CALL
from ocr_engine.exceptions.openai_exceptions import MissingOpenAIConfigurationError
from ocr_engine.models.insights_extraction import (
    Insight,
    InsightsExtractionDiagnostics,
    InsightsExtractionResult,
)
from ocr_engine.models.table_normalization import NormalizationResult
from ocr_engine.pipeline.exceptions import PipelineLayerPartialFailure
from ocr_engine.services.chunk_builder import ChunkBuilder
from ocr_engine.services.chunk_ranker import ChunkRanker
from ocr_engine.services.insights_extractor import InsightsExtractor
from ocr_engine.services.interfaces.insights_extractor import IInsightsExtractor
from ocr_engine.services.narrative_text_extractor import NarrativeTextExtractor
from ocr_engine.services.prompt_builders.insights_prompt_builder import (
    InsightsPromptBuilder,
)
from ocr_engine.services.section_identifier import SectionIdentifier
from shared.models.company_context import CompanyContext

logger = logging.getLogger(__name__)


class OpenAIInsightsExtractor(IInsightsExtractor):
    """Extract source-backed business insights from annual reports using OpenAI."""

    def __init__(
        self,
        *,
        client: Any | None = None,
        api_key: str | None = OPENAI_API_KEY,
        model: str = OPENAI_MODEL,
        narrative_text_extractor: NarrativeTextExtractor | None = None,
        section_identifier: SectionIdentifier | None = None,
        chunk_builder: ChunkBuilder | None = None,
        chunk_ranker: ChunkRanker | None = None,
        prompt_builder: InsightsPromptBuilder | None = None,
        insights_extractor: InsightsExtractor | None = None,
        max_retries: int = OPENAI_INSIGHTS_MAX_RETRIES,
        retry_backoff_seconds: float = OPENAI_INSIGHTS_RETRY_BACKOFF_SECONDS,
        request_timeout_seconds: float = OPENAI_INSIGHTS_REQUEST_TIMEOUT_SECONDS,
        chunks_per_llm_call: int = INSIGHTS_CHUNKS_PER_LLM_CALL,
        log: logging.Logger | None = None,
    ) -> None:
        """Initialize the insights extractor with injectable dependencies."""

        if insights_extractor is None and not api_key:
            raise MissingOpenAIConfigurationError(
                "OPENAI_API_KEY must be configured for insights extraction."
            )
        if chunks_per_llm_call < 1:
            raise ValueError("chunks_per_llm_call must be at least 1.")

        self._logger = log or logger
        self._narrative_text_extractor = (
            narrative_text_extractor or NarrativeTextExtractor(log=self._logger)
        )
        self._section_identifier = section_identifier or SectionIdentifier()
        self._chunk_builder = chunk_builder or ChunkBuilder()
        self._chunk_ranker = chunk_ranker or ChunkRanker()
        self._prompt_builder = prompt_builder or InsightsPromptBuilder()
        self._chunks_per_llm_call = chunks_per_llm_call

        if insights_extractor is not None:
            self._insights_extractor = insights_extractor
        else:
            openai_client = client or self._create_openai_client(api_key or "")
            self._insights_extractor = InsightsExtractor(
                client=openai_client,
                model=model,
                max_retries=max_retries,
                retry_backoff_seconds=retry_backoff_seconds,
                request_timeout_seconds=request_timeout_seconds,
                log=self._logger,
            )

    def extract_insights_for_context(self, context: CompanyContext) -> CompanyContext:
        """Extract insights for each report and store results by report year.

        The method reads ``context.normalization_results[report.year]`` and
        writes to ``context.insights_results[report.year]``. Each annual report
        is processed independently, so repeated insight areas across years do
        not overwrite one another.
        """

        self._logger.info(
            "Starting insights extraction for company context",
            extra={
                "company_name": context.company_name,
                "report_years": [report.year for report in context.reports],
            },
        )

        failures: list[str] = []
        for report in context.reports:
            try:
                normalization_result = context.normalization_results.get(report.year)
                if normalization_result is None:
                    raise ValueError(
                        "Missing normalization result for report year "
                        f"{report.year}."
                    )

                self._ensure_normalization_matches_year(
                    report.year,
                    normalization_result,
                )
                self._logger.info(
                    "Extracting insights for report year %s",
                    report.year,
                    extra={
                        "company_name": context.company_name,
                        "year": report.year,
                        "file_path": report.file_path,
                    },
                )
                context.insights_results[report.year] = (
                    self._extract_insights_for_year(
                        pdf_path=report.file_path,
                        normalization_result=normalization_result,
                        report_year=report.year,
                    )
                )
            except Exception as exc:
                failures.append(
                    f"Report year {report.year} failed insights extraction: "
                    f"{_error_message(exc)}"
                )
                context.insights_results[report.year] = InsightsExtractionResult(
                    insights=[],
                )
                self._logger.exception(
                    "Insights extraction failed for report; continuing",
                    extra={
                        "company_name": context.company_name,
                        "year": report.year,
                        "file_path": report.file_path,
                    },
                )
                continue

        self._logger.info(
            "Company context insights extraction complete",
            extra={
                "company_name": context.company_name,
                "result_years": sorted(context.insights_results),
            },
        )
        if failures:
            raise PipelineLayerPartialFailure(failures, context=context)
        return context

    def process(self, context: CompanyContext) -> CompanyContext:
        """Run insights extraction as a pipeline layer."""

        return self.extract_insights_for_context(context)

    def extract_insights(
        self,
        pdf_path: str,
        normalization_result: NormalizationResult,
    ) -> InsightsExtractionResult:
        """Extract concise, source-traceable business insights."""

        report_year = self._extract_year(normalization_result)
        return self._extract_insights_for_year(
            pdf_path=pdf_path,
            normalization_result=normalization_result,
            report_year=report_year,
        )

    def _extract_insights_for_year(
        self,
        *,
        pdf_path: str,
        normalization_result: NormalizationResult,
        report_year: int,
    ) -> InsightsExtractionResult:
        """Extract insights for one report year."""

        self._ensure_normalization_matches_year(report_year, normalization_result)
        self._logger.info("Starting insights extraction", extra={"pdf_path": pdf_path})

        pages = self._narrative_text_extractor.extract(pdf_path)
        section_pages = self._section_identifier.identify_sections(pages)
        chunks = self._chunk_builder.build_chunks(section_pages)
        ranked_chunks = self._chunk_ranker.rank_chunks(chunks, normalization_result)
        metric_context = self._chunk_ranker.extract_metric_context(normalization_result)
        diagnostics = self._build_diagnostics(
            pages=pages,
            section_pages=section_pages,
            chunks=chunks,
            ranked_chunks=ranked_chunks,
            insights=[],
            llm_call_count=0,
        )

        self._logger.info(
            "Insights preprocessing diagnostics",
            extra=diagnostics.model_dump(),
        )

        if not ranked_chunks:
            self._logger.info(
                "No relevant narrative chunks found for insights extraction",
                extra={"pdf_path": pdf_path},
            )
            return InsightsExtractionResult(insights=[], diagnostics=diagnostics)

        ranked_chunks = [
            type(chunk)(
                page_number=chunk.page_number,
                source_section=chunk.source_section,
                text=chunk.text,
                year=chunk.year or report_year,
                score=chunk.score,
            )
            for chunk in ranked_chunks
        ]

        collected_insights: list[Insight] = []
        llm_call_count = 0
        for chunk_batch in _batched(ranked_chunks, self._chunks_per_llm_call):
            llm_call_count += 1
            messages = self._prompt_builder.build_messages(
                chunks=chunk_batch,
                metric_context=metric_context,
                report_year=report_year,
            )
            batch_result = self._insights_extractor.extract(messages)
            batch_result = self._ensure_insights_use_source_report_year(
                batch_result,
                report_year,
            )
            batch_result = self._filter_insights_by_ranked_chunks(
                batch_result,
                ranked_chunks,
            )
            collected_insights.extend(batch_result.insights)

        result = self._deduplicate_insights(
            InsightsExtractionResult(insights=collected_insights)
        )
        diagnostics = self._build_diagnostics(
            pages=pages,
            section_pages=section_pages,
            chunks=chunks,
            ranked_chunks=ranked_chunks,
            insights=result.insights,
            llm_call_count=llm_call_count,
        )
        result = result.model_copy(update={"diagnostics": diagnostics})

        self._logger.info(
            "Insights extraction complete",
            extra=diagnostics.model_dump(),
        )
        return result

    @classmethod
    def _extract_year(cls, normalization_result: NormalizationResult) -> int:
        """Return the reporting year from OCR normalization output."""

        years = cls._normalization_years(normalization_result)
        if not years:
            raise ValueError(
                "normalization_result must include at least one table or mapping "
                "with year."
            )
        if len(years) > 1:
            raise ValueError(
                "Insights extraction input must contain a single report year. "
                f"Received years: {sorted(years)}."
            )
        return next(iter(years))

    @classmethod
    def _ensure_normalization_matches_year(
        cls,
        year: int,
        normalization_result: NormalizationResult,
    ) -> None:
        """Ensure a context year bucket contains only one report year's data."""

        result_years = cls._normalization_years(normalization_result)
        mismatched_years = result_years - {year}
        if mismatched_years:
            raise ValueError(
                "Insights normalization input for report year "
                f"{year} contains data from other years: "
                f"{sorted(mismatched_years)}."
            )

    @staticmethod
    def _normalization_years(normalization_result: NormalizationResult) -> set[int]:
        """Return all source report years represented by normalization output."""

        return {
            table.source_report_year for table in normalization_result.tables
        } | {
            mapping.source_report_year for mapping in normalization_result.mappings
        } | {
            metric_value.source_report_year
            for metric_value in normalization_result.metric_values
        }

    def _ensure_insights_use_source_report_year(
        self,
        result: InsightsExtractionResult,
        report_year: int,
    ) -> InsightsExtractionResult:
        """Attach the authoritative source report year to every insight."""

        insights: list[Insight] = []
        for insight in result.insights:
            if insight.source_report_year != report_year:
                self._logger.warning(
                    "Insight source report year corrected",
                    extra={
                        "reported_source_report_year": insight.source_report_year,
                        "source_report_year": report_year,
                        "area": insight.area,
                    },
                )
            insights.append(
                insight.model_copy(update={"source_report_year": report_year})
            )

        return InsightsExtractionResult(insights=insights)

    def _filter_insights_by_ranked_chunks(
        self,
        result: InsightsExtractionResult,
        ranked_chunks: list[Any],
    ) -> InsightsExtractionResult:
        """Accept only insights whose source reference exists in ranked chunks."""

        valid_sources = {
            (chunk.page_number, _normalize_source_section(chunk.source_section))
            for chunk in ranked_chunks
        }
        insights: list[Insight] = []
        for insight in result.insights:
            source_key = (
                insight.page_number,
                _normalize_source_section(insight.source_section),
            )
            if source_key not in valid_sources:
                self._logger.warning(
                    "Insight source reference rejected",
                    extra={
                        "page_number": insight.page_number,
                        "source_section": insight.source_section,
                        "source_report_year": insight.source_report_year,
                        "area": insight.area,
                    },
                )
                continue
            insights.append(insight)

        return InsightsExtractionResult(insights=insights)

    @staticmethod
    def _deduplicate_insights(
        result: InsightsExtractionResult,
    ) -> InsightsExtractionResult:
        """Remove duplicates after source-report-year normalization."""

        insights: list[Insight] = []
        seen: set[tuple[str, str, str, int, int, int]] = set()
        for insight in result.insights:
            key = (
                insight.area.strip().lower(),
                insight.takeaway.strip().lower(),
                insight.source_section.strip().lower(),
                insight.value_year,
                insight.source_report_year,
                insight.page_number,
            )
            if key in seen:
                continue
            seen.add(key)
            insights.append(insight)

        return InsightsExtractionResult(insights=insights)

    def _build_diagnostics(
        self,
        *,
        pages: list[Any],
        section_pages: list[Any],
        chunks: list[Any],
        ranked_chunks: list[Any],
        insights: list[Insight],
        llm_call_count: int,
    ) -> InsightsExtractionDiagnostics:
        """Build trace diagnostics for one report's insights extraction flow."""

        total_pages_processed = getattr(
            self._narrative_text_extractor,
            "last_total_pages_processed",
            0,
        ) or _max_page_number(pages)

        return InsightsExtractionDiagnostics(
            total_pages_processed=total_pages_processed,
            pages_with_text=len(pages),
            total_text_characters=sum(len(getattr(page, "text", "")) for page in pages),
            section_pages=len(section_pages),
            total_chunks_created=len(chunks),
            chunk_size=getattr(self._chunk_builder, "max_characters", 0),
            chunk_overlap=getattr(self._chunk_builder, "overlap_characters", 0),
            retrieval_strategy=getattr(
                self._chunk_ranker,
                "retrieval_strategy",
                "custom_ranker",
            ),
            top_k=getattr(self._chunk_ranker, "max_chunks", None),
            chunks_sent_to_llm=len(ranked_chunks),
            llm_call_count=llm_call_count,
            generated_insights=len(insights),
            section_page_count_by_section=_count_by_attribute(
                section_pages,
                "section",
            ),
            chunk_count_by_section=_count_by_attribute(chunks, "source_section"),
            ranked_chunk_count_by_section=_count_by_attribute(
                ranked_chunks,
                "source_section",
            ),
            insight_count_by_section=_count_by_attribute(insights, "source_section"),
        )

    @staticmethod
    def _create_openai_client(api_key: str) -> Any:
        """Create a real OpenAI SDK client."""

        try:
            from openai import OpenAI
        except ImportError as exc:
            raise RuntimeError(
                "openai is required for OpenAI insights extraction."
            ) from exc

        return OpenAI(api_key=api_key)


def _normalize_source_section(source_section: str) -> str:
    """Normalize section names for source-reference validation."""

    return " ".join(source_section.strip().lower().split())


def _batched(chunks: list[Any], batch_size: int) -> list[list[Any]]:
    """Split ranked chunks into deterministic LLM request batches."""

    return [
        chunks[index : index + batch_size]
        for index in range(0, len(chunks), batch_size)
    ]


def _max_page_number(pages: list[Any]) -> int:
    """Return the highest page number seen in extracted pages."""

    page_numbers = [
        getattr(page, "page_number", 0)
        for page in pages
        if isinstance(getattr(page, "page_number", 0), int)
    ]
    return max(page_numbers, default=0)


def _count_by_attribute(items: list[Any], attribute: str) -> dict[str, int]:
    """Return a stable count by a string-like attribute."""

    counter: Counter[str] = Counter()
    for item in items:
        value = getattr(item, attribute, None)
        if value is None:
            continue
        counter[str(value)] += 1
    return dict(sorted(counter.items()))


def _error_message(exc: Exception) -> str:
    """Return a non-empty error message for result metadata."""

    return str(exc) or exc.__class__.__name__
