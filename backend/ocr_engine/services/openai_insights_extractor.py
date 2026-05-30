"""OpenAI-backed OCR insights extraction service."""

from __future__ import annotations

import logging
from typing import Any

from ocr_engine.constants.ai_constants import (
    OPENAI_API_KEY,
    OPENAI_INSIGHTS_MAX_RETRIES,
    OPENAI_INSIGHTS_RETRY_BACKOFF_SECONDS,
    OPENAI_MODEL,
)
from ocr_engine.exceptions.openai_exceptions import MissingOpenAIConfigurationError
from ocr_engine.models.insights_extraction import Insight, InsightsExtractionResult
from ocr_engine.models.table_normalization import NormalizationResult
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
        log: logging.Logger | None = None,
    ) -> None:
        """Initialize the insights extractor with injectable dependencies."""

        if insights_extractor is None and not api_key:
            raise MissingOpenAIConfigurationError(
                "OPENAI_API_KEY must be configured for insights extraction."
            )

        self._logger = log or logger
        self._narrative_text_extractor = (
            narrative_text_extractor or NarrativeTextExtractor(log=self._logger)
        )
        self._section_identifier = section_identifier or SectionIdentifier()
        self._chunk_builder = chunk_builder or ChunkBuilder()
        self._chunk_ranker = chunk_ranker or ChunkRanker()
        self._prompt_builder = prompt_builder or InsightsPromptBuilder()

        if insights_extractor is not None:
            self._insights_extractor = insights_extractor
        else:
            openai_client = client or self._create_openai_client(api_key or "")
            self._insights_extractor = InsightsExtractor(
                client=openai_client,
                model=model,
                max_retries=max_retries,
                retry_backoff_seconds=retry_backoff_seconds,
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

        for report in context.reports:
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
            context.insights_results[report.year] = self._extract_insights_for_year(
                pdf_path=report.file_path,
                normalization_result=normalization_result,
                report_year=report.year,
            )

        self._logger.info(
            "Company context insights extraction complete",
            extra={
                "company_name": context.company_name,
                "result_years": sorted(context.insights_results),
            },
        )
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

        if not ranked_chunks:
            self._logger.info(
                "No relevant narrative chunks found for insights extraction",
                extra={"pdf_path": pdf_path},
            )
            return InsightsExtractionResult(insights=[])

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

        messages = self._prompt_builder.build_messages(
            chunks=ranked_chunks,
            metric_context=metric_context,
            report_year=report_year,
        )
        result = self._insights_extractor.extract(messages)
        result = self._ensure_insights_use_source_report_year(result, report_year)

        self._logger.info(
            "Insights extraction complete",
            extra={"insight_count": len(result.insights)},
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
        """Ensure a context year bucket contains only normalization data for that year."""

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
