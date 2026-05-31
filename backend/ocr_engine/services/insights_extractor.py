"""OpenAI structured-output request handling for insights extraction."""

from __future__ import annotations

import json
import logging
import time
from typing import Any, Callable

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from ocr_engine.exceptions.openai_exceptions import (
    OpenAIInsightsExtractionError,
    OpenAIResponseValidationError,
)
from ocr_engine.models.insights_extraction import Insight, InsightsExtractionResult

logger = logging.getLogger(__name__)


class _InsightsPayload(BaseModel):
    """Validated structured output returned by OpenAI."""

    model_config = ConfigDict(extra="forbid")

    insights: list[Insight] = Field(default_factory=list)


class InsightsExtractor:
    """Call OpenAI and parse structured business insight responses."""

    _RESPONSE_FORMAT = {
        "type": "json_schema",
        "name": "business_insights_extraction",
        "strict": True,
        "schema": {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "insights": {
                    "type": "array",
                    "description": "Concise source-backed business insights.",
                    "items": {
                        "type": "object",
                        "additionalProperties": False,
                        "properties": {
                            "area": {"type": "string"},
                            "takeaway": {"type": "string"},
                            "source_section": {"type": "string"},
                            "value_year": {"type": "integer", "minimum": 1900},
                            "source_report_year": {
                                "type": "integer",
                                "minimum": 1900,
                            },
                            "page_number": {"type": "integer", "minimum": 1},
                            "confidence": {
                                "type": "number",
                                "minimum": 0,
                                "maximum": 1,
                            },
                        },
                        "required": [
                            "area",
                            "takeaway",
                            "source_section",
                            "value_year",
                            "source_report_year",
                            "page_number",
                            "confidence",
                        ],
                    },
                }
            },
            "required": ["insights"],
        },
    }

    def __init__(
        self,
        *,
        client: Any,
        model: str,
        max_retries: int,
        retry_backoff_seconds: float,
        request_timeout_seconds: float = 60.0,
        sleep: Callable[[float], None] = time.sleep,
        log: logging.Logger | None = None,
    ) -> None:
        """Initialize the OpenAI request handler."""

        if max_retries < 1:
            raise ValueError("max_retries must be at least 1.")
        if retry_backoff_seconds < 0:
            raise ValueError("retry_backoff_seconds cannot be negative.")
        if request_timeout_seconds <= 0:
            raise ValueError("request_timeout_seconds must be greater than 0.")

        self._client = client
        self._model = model
        self._max_retries = max_retries
        self._retry_backoff_seconds = retry_backoff_seconds
        self._request_timeout_seconds = request_timeout_seconds
        self._sleep = sleep
        self._logger = log or logger

    def extract(self, messages: list[dict[str, str]]) -> InsightsExtractionResult:
        """Call OpenAI with retry handling and parse structured output."""

        response = self._create_response_with_retries(messages)
        insights = self._parse_insights(response)
        return InsightsExtractionResult(insights=insights)

    def _create_response_with_retries(
        self,
        messages: list[dict[str, str]],
    ) -> Any:
        """Call OpenAI Responses API with bounded retry logic."""

        last_error: Exception | None = None
        for attempt in range(1, self._max_retries + 1):
            try:
                return self._client.responses.create(
                    model=self._model,
                    input=messages,
                    text={"format": self._RESPONSE_FORMAT},
                    timeout=self._request_timeout_seconds,
                )
            except Exception as exc:
                last_error = exc
                if _is_terminal_client_error(exc):
                    self._logger.warning(
                        "OpenAI insights extraction terminal client error",
                        extra={
                            "attempt": attempt,
                            "status_code": _status_code(exc),
                        },
                        exc_info=True,
                    )
                    raise OpenAIInsightsExtractionError(
                        "OpenAI insights extraction failed with terminal "
                        "client error."
                    ) from exc

                self._logger.warning(
                    "OpenAI insights extraction request failed",
                    extra={
                        "attempt": attempt,
                        "max_retries": self._max_retries,
                    },
                    exc_info=True,
                )
                if attempt < self._max_retries:
                    self._sleep(self._retry_backoff_seconds * attempt)

        raise OpenAIInsightsExtractionError(
            "OpenAI insights extraction failed after retries."
        ) from last_error

    def _parse_insights(self, response: Any) -> list[Insight]:
        """Parse and validate structured JSON insights output."""

        output_text = self._extract_output_text(response)
        try:
            payload = json.loads(output_text)
            validated = _InsightsPayload.model_validate(payload)
        except (json.JSONDecodeError, TypeError, ValidationError) as exc:
            raise OpenAIResponseValidationError(
                "OpenAI insights extraction response did not match schema."
            ) from exc

        return self._deduplicate(validated.insights)

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
    def _deduplicate(insights: list[Insight]) -> list[Insight]:
        """Remove duplicate insights while preserving response order."""

        unique_insights: list[Insight] = []
        seen: set[tuple[str, str, int]] = set()
        for insight in insights:
            key = (
                insight.area.strip().lower(),
                insight.takeaway.strip().lower(),
                insight.value_year,
                insight.source_report_year,
                insight.page_number,
            )
            if key in seen:
                continue
            unique_insights.append(insight)
            seen.add(key)
        return unique_insights


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
