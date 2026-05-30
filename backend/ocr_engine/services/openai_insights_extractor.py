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
from ocr_engine.models.insights_extraction import InsightsExtractionResult
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

        if insights_extractor is None and (not api_key or api_key == "DUMMY_KEY"):
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

    def extract_insights(
        self,
        pdf_path: str,
        normalization_result: NormalizationResult,
    ) -> InsightsExtractionResult:
        """Extract concise, source-traceable business insights."""

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

        messages = self._prompt_builder.build_messages(
            chunks=ranked_chunks,
            metric_context=metric_context,
        )
        result = self._insights_extractor.extract(messages)

        self._logger.info(
            "Insights extraction complete",
            extra={"insight_count": len(result.insights)},
        )
        return result

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
