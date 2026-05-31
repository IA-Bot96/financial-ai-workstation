"""OpenAI-backed financial table classification service."""

from __future__ import annotations

import json
import logging
import time
from typing import Any, Callable

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from ocr_engine.constants.ai_constants import (
    OPENAI_API_KEY,
    OPENAI_CLASSIFICATION_MAX_RETRIES,
    OPENAI_CLASSIFICATION_REQUEST_TIMEOUT_SECONDS,
    OPENAI_CLASSIFICATION_RETRY_BACKOFF_SECONDS,
    OPENAI_MODEL,
)
from ocr_engine.exceptions.openai_exceptions import (
    MissingOpenAIConfigurationError,
    OpenAITableClassificationError,
    OpenAIResponseValidationError,
)
from ocr_engine.models.financial_table_classification import (
    FinancialTableClassificationResult,
    PageTableType,
    TableType,
)
from ocr_engine.models.table_detection_result import FailedPage, TableDetectionResult
from ocr_engine.services.interfaces.table_classifier import ITableClassifier
from ocr_engine.services.prompt_builders.table_classification_prompt_builder import (
    TableClassificationPromptBuilder,
)
from shared.models.company_context import CompanyContext

logger = logging.getLogger(__name__)


class _TableClassificationPayload(BaseModel):
    """Validated structured output returned by OpenAI for one page."""

    model_config = ConfigDict(extra="forbid")

    table_types: list[TableType] = Field(default_factory=list)


class OpenAITableClassifier(ITableClassifier):
    """Classify detected financial tables using OpenAI Structured Outputs."""

    _RESPONSE_FORMAT = {
        "type": "json_schema",
        "name": "financial_table_classification",
        "strict": True,
        "schema": {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "table_types": {
                    "type": "array",
                    "description": "All financial table types present on the page.",
                    "items": {"type": "string", "minLength": 1},
                }
            },
            "required": ["table_types"],
        },
    }

    def __init__(
        self,
        *,
        client: Any | None = None,
        api_key: str | None = OPENAI_API_KEY,
        model: str = OPENAI_MODEL,
        prompt_builder: TableClassificationPromptBuilder | None = None,
        pdf_loader: Callable[[str], Any] | None = None,
        max_retries: int = OPENAI_CLASSIFICATION_MAX_RETRIES,
        retry_backoff_seconds: float = OPENAI_CLASSIFICATION_RETRY_BACKOFF_SECONDS,
        request_timeout_seconds: float = (
            OPENAI_CLASSIFICATION_REQUEST_TIMEOUT_SECONDS
        ),
        sleep: Callable[[float], None] = time.sleep,
        log: logging.Logger | None = None,
    ) -> None:
        """Initialize the OpenAI table classifier with injectable dependencies."""

        if not api_key:
            raise MissingOpenAIConfigurationError(
                "OPENAI_API_KEY must be configured for table classification."
            )
        if max_retries < 1:
            raise ValueError("max_retries must be at least 1.")
        if retry_backoff_seconds < 0:
            raise ValueError("retry_backoff_seconds cannot be negative.")
        if request_timeout_seconds <= 0:
            raise ValueError("request_timeout_seconds must be greater than 0.")

        self._api_key = api_key
        self._model = model
        self._prompt_builder = prompt_builder or TableClassificationPromptBuilder()
        self._pdf_loader = pdf_loader or self._load_pdf_document
        self._max_retries = max_retries
        self._retry_backoff_seconds = retry_backoff_seconds
        self._request_timeout_seconds = request_timeout_seconds
        self._sleep = sleep
        self._logger = log or logger
        self._client = client or self._create_openai_client(api_key)

    def classify_tables_for_context(self, context: CompanyContext) -> CompanyContext:
        """Classify detected tables for each report and store results by year.

        The method reads ``context.table_detection_results[report.year]`` and
        writes the resulting classification to
        ``context.classification_results[report.year]``. Each report year is
        processed independently.
        """

        self._logger.info(
            "Starting financial table classification for company context",
            extra={
                "company_name": context.company_name,
                "report_years": [report.year for report in context.reports],
            },
        )

        for report in context.reports:
            table_detection_result = context.table_detection_results.get(report.year)
            if table_detection_result is None:
                raise ValueError(
                    "Missing table detection result for report year "
                    f"{report.year}."
                )

            self._logger.info(
                "Classifying detected tables for report year %s",
                report.year,
                extra={
                    "company_name": context.company_name,
                    "year": report.year,
                    "file_path": report.file_path,
                },
            )
            context.classification_results[report.year] = self.classify_tables(
                pdf_path=report.file_path,
                table_detection_result=table_detection_result,
            )

        self._logger.info(
            "Company context financial table classification complete",
            extra={
                "company_name": context.company_name,
                "result_years": sorted(context.classification_results),
            },
        )
        return context

    def process(self, context: CompanyContext) -> CompanyContext:
        """Run financial table classification as a pipeline layer."""

        return self.classify_tables_for_context(context)

    def classify_tables(
        self,
        pdf_path: str,
        table_detection_result: TableDetectionResult,
    ) -> FinancialTableClassificationResult:
        """Classify all financial table types on detected PDF pages."""

        page_table_types: list[PageTableType] = []
        failed_pages: list[FailedPage] = []
        document = None

        try:
            document = self._pdf_loader(pdf_path)
        except Exception:
            self._logger.exception(
                "Failed to open PDF for table classification",
                extra={"pdf_path": pdf_path},
            )
            raise

        try:
            for detected_page in table_detection_result.detected_pages:
                page_number = detected_page.page_number
                self._logger.info(
                    "Classifying tables on page %s",
                    page_number,
                    extra={
                        "page": page_number,
                        "tables_detected": detected_page.tables_detected,
                    },
                )

                try:
                    page_text = self._extract_page_text(document, page_number)
                    table_types = self._classify_page(
                        page_number=page_number,
                        tables_detected=detected_page.tables_detected,
                        page_text=page_text,
                    )
                    page_table_types.append(
                        PageTableType(
                            year=detected_page.year,
                            page_number=page_number,
                            table_types=table_types,
                        )
                    )
                except Exception as exc:
                    failed_pages.append(
                        FailedPage(
                            year=detected_page.year,
                            page_number=page_number,
                            error_message=_error_message(exc),
                        )
                    )
                    self._logger.exception(
                        "Page skipped due to classification error",
                        extra={"page": page_number},
                    )
                    continue
        finally:
            close = getattr(document, "close", None)
            if callable(close):
                close()

        result = FinancialTableClassificationResult(
            page_table_types=page_table_types,
            failed_pages=failed_pages,
        )
        self._logger.info(
            "Table classification complete",
            extra={
                "pages_classified": len(result.page_table_types),
                "failed_pages": [
                    failed_page.model_dump() for failed_page in result.failed_pages
                ],
            },
        )
        return result

    def _classify_page(
        self,
        *,
        page_number: int,
        tables_detected: int,
        page_text: str,
    ) -> list[str]:
        """Classify table types for a single page with retry handling."""

        messages = self._prompt_builder.build_messages(
            page_number=page_number,
            tables_detected=tables_detected,
            page_text=page_text,
        )
        response = self._create_response_with_retries(
            messages=messages,
            page_number=page_number,
        )
        return response

    def _create_response_with_retries(
        self,
        *,
        messages: list[dict[str, str]],
        page_number: int,
    ) -> list[str]:
        """Call OpenAI Responses API and validate output with bounded retries."""

        last_error: Exception | None = None
        for attempt in range(1, self._max_retries + 1):
            try:
                response = self._client.responses.create(
                    model=self._model,
                    input=messages,
                    text={"format": self._RESPONSE_FORMAT},
                    timeout=self._request_timeout_seconds,
                )
                return self._parse_table_types(response)
            except OpenAIResponseValidationError as exc:
                last_error = exc
                self._logger.warning(
                    "OpenAI table classification response invalid",
                    extra={
                        "page": page_number,
                        "attempt": attempt,
                        "max_retries": self._max_retries,
                    },
                    exc_info=True,
                )
            except Exception as exc:
                last_error = exc
                if _is_terminal_client_error(exc):
                    self._logger.warning(
                        "OpenAI table classification terminal client error",
                        extra={
                            "page": page_number,
                            "attempt": attempt,
                            "status_code": _status_code(exc),
                        },
                        exc_info=True,
                    )
                    raise OpenAITableClassificationError(
                        "OpenAI table classification failed with terminal "
                        f"client error for page {page_number}."
                    ) from exc

                self._logger.warning(
                    "OpenAI table classification request failed",
                    extra={
                        "page": page_number,
                        "attempt": attempt,
                        "max_retries": self._max_retries,
                    },
                    exc_info=True,
                )
                if attempt < self._max_retries:
                    self._sleep(self._retry_backoff_seconds * attempt)

        raise OpenAITableClassificationError(
            f"OpenAI table classification failed for page {page_number}."
        ) from last_error

    def _parse_table_types(self, response: Any) -> list[str]:
        """Parse and validate structured JSON table classification output."""

        output_text = self._extract_output_text(response)
        try:
            payload = json.loads(output_text)
            validated = _TableClassificationPayload.model_validate(payload)
        except (json.JSONDecodeError, TypeError, ValidationError) as exc:
            raise OpenAIResponseValidationError(
                "OpenAI table classification response did not match schema."
            ) from exc

        return self._deduplicate(validated.table_types)

    @staticmethod
    def _extract_output_text(response: Any) -> str:
        """Extract JSON text from an OpenAI Responses API response object."""

        output_text = getattr(response, "output_text", None)
        if isinstance(output_text, str):
            return output_text

        output = getattr(response, "output", None)
        if output:
            text_parts: list[str] = []
            for output_item in output:
                for content_item in getattr(output_item, "content", []) or []:
                    text = getattr(content_item, "text", None)
                    if isinstance(text, str):
                        text_parts.append(text)
            if text_parts:
                return "".join(text_parts)

        raise OpenAIResponseValidationError(
            "OpenAI response did not include output text."
        )

    @staticmethod
    def _deduplicate(table_types: list[str]) -> list[str]:
        """Remove duplicate table type labels while preserving response order."""

        unique_table_types: list[str] = []
        seen: set[str] = set()
        for table_type in table_types:
            if table_type not in seen:
                unique_table_types.append(table_type)
                seen.add(table_type)
        return unique_table_types

    @staticmethod
    def _extract_page_text(document: Any, page_number: int) -> str:
        """Extract text from a one-based PDF page using PyMuPDF."""

        page = document.load_page(page_number - 1)
        return page.get_text("text")

    @staticmethod
    def _load_pdf_document(pdf_path: str) -> Any:
        """Open a PDF document with PyMuPDF."""

        try:
            import fitz
        except ImportError as exc:
            raise RuntimeError(
                "PyMuPDF is required for OpenAI table classification."
            ) from exc

        return fitz.open(pdf_path)

    @staticmethod
    def _create_openai_client(api_key: str) -> Any:
        """Create a real OpenAI SDK client."""

        try:
            from openai import OpenAI
        except ImportError as exc:
            raise RuntimeError(
                "openai is required for OpenAI table classification."
            ) from exc

        return OpenAI(api_key=api_key)


def _status_code(exc: Exception) -> int | None:
    """Extract an HTTP status code from OpenAI SDK or test-double errors."""

    status_code = getattr(exc, "status_code", None)
    if isinstance(status_code, int):
        return status_code

    response = getattr(exc, "response", None)
    response_status_code = getattr(response, "status_code", None)
    if isinstance(response_status_code, int):
        return response_status_code

    return None


def _is_terminal_client_error(exc: Exception) -> bool:
    """Return True for non-retryable HTTP 4xx errors."""

    status_code = _status_code(exc)
    return status_code is not None and 400 <= status_code < 500


def _error_message(exc: Exception) -> str:
    """Return a non-empty error message for page failure metadata."""

    return str(exc) or exc.__class__.__name__
