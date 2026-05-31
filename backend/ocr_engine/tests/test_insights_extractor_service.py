"""Unit tests for OpenAI structured insights extraction request handling."""

import sys
from pathlib import Path

import pytest

BACKEND_DIR = Path(__file__).resolve().parents[2]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from ocr_engine.exceptions.openai_exceptions import (
    OpenAIInsightsExtractionError,
    OpenAIResponseValidationError,
)
from ocr_engine.services.insights_extractor import InsightsExtractor


class FakeResponse:
    def __init__(self, output_text: str) -> None:
        self.output_text = output_text


class FakeTerminalOpenAIError(RuntimeError):
    status_code = 400


class FakeResponses:
    def __init__(self, responses: list[object]) -> None:
        self._responses = responses
        self.calls: list[dict[str, object]] = []

    def create(self, **kwargs: object) -> object:
        self.calls.append(kwargs)
        response = self._responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response


class FakeClient:
    def __init__(self, responses: list[object]) -> None:
        self.responses = FakeResponses(responses)


def test_insights_extractor_uses_structured_output_schema() -> None:
    client = FakeClient(
        [
            FakeResponse(
                """
                {
                  "insights": [
                    {
                      "area": "Debt",
                      "takeaway": "Borrowings increased to finance expansion.",
                      "source_section": "Management Discussion & Analysis",
                      "value_year": 2024,
                      "source_report_year": 2025,
                      "page_number": 84,
                      "confidence": 0.91
                    }
                  ]
                }
                """
            )
        ]
    )
    extractor = InsightsExtractor(
        client=client,
        model="gpt-5",
        max_retries=1,
        retry_backoff_seconds=0,
    )

    result = extractor.extract(messages=[{"role": "user", "content": "Extract."}])

    assert result.model_dump(exclude={"diagnostics"}) == {
        "insights": [
            {
                "area": "Debt",
                "takeaway": "Borrowings increased to finance expansion.",
                "source_section": "Management Discussion & Analysis",
                "value_year": 2024,
                "source_report_year": 2025,
                "page_number": 84,
                "confidence": 0.91,
            }
        ]
    }
    request = client.responses.calls[0]
    assert request["model"] == "gpt-5"
    assert request["text"]["format"]["type"] == "json_schema"
    assert request["timeout"] == 60.0


def test_insights_extractor_passes_configured_request_timeout() -> None:
    client = FakeClient([FakeResponse('{"insights": []}')])
    extractor = InsightsExtractor(
        client=client,
        model="gpt-5",
        max_retries=1,
        retry_backoff_seconds=0,
        request_timeout_seconds=12.5,
    )

    extractor.extract(messages=[{"role": "user", "content": "Extract."}])

    assert client.responses.calls[0]["timeout"] == 12.5


def test_insights_extractor_retries_failures() -> None:
    client = FakeClient(
        [
            RuntimeError("temporary failure"),
            FakeResponse('{"insights": []}'),
        ]
    )
    sleeps: list[float] = []
    extractor = InsightsExtractor(
        client=client,
        model="gpt-5",
        max_retries=2,
        retry_backoff_seconds=0.5,
        sleep=sleeps.append,
    )

    result = extractor.extract(messages=[{"role": "user", "content": "Extract."}])

    assert result.insights == []
    assert len(client.responses.calls) == 2
    assert sleeps == [0.5]


def test_insights_extractor_raises_after_retries() -> None:
    extractor = InsightsExtractor(
        client=FakeClient([RuntimeError("failed")]),
        model="gpt-5",
        max_retries=1,
        retry_backoff_seconds=0,
    )

    with pytest.raises(OpenAIInsightsExtractionError):
        extractor.extract(messages=[{"role": "user", "content": "Extract."}])


def test_insights_extractor_does_not_retry_terminal_4xx_errors() -> None:
    client = FakeClient([FakeTerminalOpenAIError("bad request")])
    extractor = InsightsExtractor(
        client=client,
        model="gpt-5",
        max_retries=3,
        retry_backoff_seconds=0,
        sleep=lambda _: None,
    )

    with pytest.raises(OpenAIInsightsExtractionError):
        extractor.extract(messages=[{"role": "user", "content": "Extract."}])

    assert len(client.responses.calls) == 1


def test_insights_extractor_validates_response_schema() -> None:
    extractor = InsightsExtractor(
        client=FakeClient([FakeResponse('{"insights": [{"area": "Debt"}]}')]),
        model="gpt-5",
        max_retries=1,
        retry_backoff_seconds=0,
    )

    with pytest.raises(OpenAIResponseValidationError):
        extractor.extract(messages=[{"role": "user", "content": "Extract."}])
