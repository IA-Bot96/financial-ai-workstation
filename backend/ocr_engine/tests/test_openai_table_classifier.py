"""Unit tests for the OpenAI table classifier service."""

import json
import logging
import sys
from pathlib import Path

import pytest

BACKEND_DIR = Path(__file__).resolve().parents[2]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from ocr_engine.exceptions.openai_exceptions import (
    MissingOpenAIConfigurationError,
    OpenAITableClassificationError,
    OpenAIResponseValidationError,
)
from ocr_engine.models.financial_table_classification import (
    FinancialTableClassificationResult,
)
from ocr_engine.models.table_detection_result import DetectedPage, TableDetectionResult
from ocr_engine.services.interfaces.table_classifier import ITableClassifier
from ocr_engine.services.openai_table_classifier import OpenAITableClassifier


class FakePage:
    def __init__(self, text: str) -> None:
        self._text = text

    def get_text(self, mode: str) -> str:
        assert mode == "text"
        return self._text


class FakeDocument:
    def __init__(self, pages: dict[int, str]) -> None:
        self._pages = pages
        self.closed = False

    def load_page(self, page_index: int) -> FakePage:
        page_number = page_index + 1
        if page_number not in self._pages:
            raise RuntimeError("page not readable")
        return FakePage(self._pages[page_number])

    def close(self) -> None:
        self.closed = True


class FakeResponse:
    def __init__(self, payload: object) -> None:
        self.output_text = json.dumps(payload)


class FakeResponsesClient:
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
        self.responses = FakeResponsesClient(responses)


def _detection_result() -> TableDetectionResult:
    return TableDetectionResult(
        detected_pages=[
            DetectedPage(page_number=20, tables_detected=2),
            DetectedPage(page_number=25, tables_detected=1),
        ],
        total_pages_processed=132,
    )


def test_openai_table_classifier_implements_interface() -> None:
    classifier = OpenAITableClassifier(
        client=FakeOpenAIClient([FakeResponse({"table_types": []})]),
        api_key="test_key",
        pdf_loader=lambda _: FakeDocument({20: "Balance Sheet"}),
    )

    assert isinstance(classifier, ITableClassifier)


def test_openai_table_classifier_requires_api_key() -> None:
    with pytest.raises(MissingOpenAIConfigurationError):
        OpenAITableClassifier(
            client=FakeOpenAIClient([]),
            api_key="DUMMY_KEY",
        )


def test_classify_tables_uses_structured_outputs_and_returns_page_types() -> None:
    client = FakeOpenAIClient(
        [
            FakeResponse({"table_types": ["balance_sheet", "debt_schedule"]}),
            FakeResponse({"table_types": ["income_statement"]}),
        ]
    )
    document = FakeDocument(
        {
            20: "Balance Sheet\nLong term financing note",
            25: "Statement of Profit or Loss\nRevenue",
        }
    )
    classifier = OpenAITableClassifier(
        client=client,
        api_key="test_key",
        model="gpt-5",
        pdf_loader=lambda _: document,
    )

    result = classifier.classify_tables(
        pdf_path="annual_report.pdf",
        table_detection_result=_detection_result(),
    )

    assert isinstance(result, FinancialTableClassificationResult)
    assert result.model_dump() == {
        "page_table_types": [
            {
                "page_number": 20,
                "table_types": ["balance_sheet", "debt_schedule"],
            },
            {
                "page_number": 25,
                "table_types": ["income_statement"],
            },
        ]
    }
    assert document.closed is True
    assert client.responses.calls[0]["model"] == "gpt-5"
    assert client.responses.calls[0]["text"] == {
        "format": OpenAITableClassifier._RESPONSE_FORMAT
    }
    assert "Statement of Profit or Loss" in client.responses.calls[1]["input"][1][
        "content"
    ]


def test_classify_tables_retries_openai_request() -> None:
    client = FakeOpenAIClient(
        [
            RuntimeError("temporary failure"),
            FakeResponse({"table_types": ["cash_flow_statement"]}),
        ]
    )
    classifier = OpenAITableClassifier(
        client=client,
        api_key="test_key",
        pdf_loader=lambda _: FakeDocument({20: "Statement of Cash Flows"}),
        max_retries=2,
        retry_backoff_seconds=0,
        sleep=lambda _: None,
    )

    result = classifier.classify_tables(
        pdf_path="annual_report.pdf",
        table_detection_result=TableDetectionResult(
            detected_pages=[DetectedPage(page_number=20, tables_detected=1)],
            total_pages_processed=30,
        ),
    )

    assert result.page_table_types[0].table_types == ["cash_flow_statement"]
    assert len(client.responses.calls) == 2


def test_classify_tables_raises_after_retry_exhaustion() -> None:
    classifier = OpenAITableClassifier(
        client=FakeOpenAIClient([RuntimeError("failure")]),
        api_key="test_key",
        pdf_loader=lambda _: FakeDocument({20: "Balance Sheet"}),
        max_retries=1,
    )

    with pytest.raises(OpenAITableClassificationError):
        classifier.classify_tables(
            pdf_path="annual_report.pdf",
            table_detection_result=TableDetectionResult(
                detected_pages=[DetectedPage(page_number=20, tables_detected=1)],
                total_pages_processed=30,
            ),
        )


def test_classify_tables_rejects_invalid_openai_response() -> None:
    classifier = OpenAITableClassifier(
        client=FakeOpenAIClient([FakeResponse({"table_types": [123]})]),
        api_key="test_key",
        pdf_loader=lambda _: FakeDocument({20: "Balance Sheet"}),
    )

    with pytest.raises(OpenAIResponseValidationError):
        classifier.classify_tables(
            pdf_path="annual_report.pdf",
            table_detection_result=TableDetectionResult(
                detected_pages=[DetectedPage(page_number=20, tables_detected=1)],
                total_pages_processed=30,
            ),
        )


def test_classify_tables_skips_unreadable_pages_and_continues(
    caplog: pytest.LogCaptureFixture,
) -> None:
    classifier = OpenAITableClassifier(
        client=FakeOpenAIClient(
            [FakeResponse({"table_types": ["income_statement"]})]
        ),
        api_key="test_key",
        pdf_loader=lambda _: FakeDocument({25: "Income Statement"}),
    )

    with caplog.at_level(logging.INFO):
        result = classifier.classify_tables(
            pdf_path="annual_report.pdf",
            table_detection_result=_detection_result(),
        )

    assert result.model_dump() == {
        "page_table_types": [
            {
                "page_number": 25,
                "table_types": ["income_statement"],
            }
        ]
    }
    assert "Classifying tables on page 20" in caplog.text
    assert "Page skipped due to classification error" in caplog.text
    assert "Table classification complete" in caplog.text
