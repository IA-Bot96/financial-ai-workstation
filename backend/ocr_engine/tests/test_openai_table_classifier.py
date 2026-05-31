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
)
from ocr_engine.models.financial_table_classification import (
    FinancialTableClassificationResult,
)
from ocr_engine.models.table_detection_result import DetectedPage, TableDetectionResult
from ocr_engine.services.interfaces.table_classifier import ITableClassifier
from ocr_engine.services.openai_table_classifier import OpenAITableClassifier
from shared.models.company_context import CompanyContext
from shared.models.report import Report


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


class FakeTextResponse:
    def __init__(self, output_text: str) -> None:
        self.output_text = output_text


class FakeTerminalOpenAIError(RuntimeError):
    status_code = 400


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
            DetectedPage(year=2024, page_number=20, tables_detected=2),
            DetectedPage(year=2024, page_number=25, tables_detected=1),
        ],
        failed_pages=[],
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
            api_key="",
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
                "year": 2024,
                "page_number": 20,
                "table_types": ["balance_sheet", "debt_schedule"],
            },
            {
                "year": 2024,
                "page_number": 25,
                "table_types": ["income_statement"],
            },
        ],
        "failed_pages": [],
    }
    assert document.closed is True
    assert client.responses.calls[0]["model"] == "gpt-5"
    assert client.responses.calls[0]["text"] == {
        "format": OpenAITableClassifier._RESPONSE_FORMAT
    }
    assert client.responses.calls[0]["timeout"] == 60.0
    assert "Statement of Profit or Loss" in client.responses.calls[1]["input"][1][
        "content"
    ]


def test_classify_tables_for_context_stores_results_by_report_year() -> None:
    client = FakeOpenAIClient(
        [
            FakeResponse({"table_types": ["balance_sheet"]}),
            FakeResponse({"table_types": ["income_statement"]}),
            FakeResponse({"table_types": ["cash_flow_statement"]}),
        ]
    )
    documents = {
        "reports/MLCF_2023.pdf": FakeDocument({10: "Balance Sheet"}),
        "reports/MLCF_2024.pdf": FakeDocument(
            {
                20: "Statement of Profit or Loss",
                25: "Statement of Cash Flows",
            }
        ),
    }
    classifier = OpenAITableClassifier(
        client=client,
        api_key="test_key",
        pdf_loader=lambda pdf_path: documents[pdf_path],
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
        table_detection_results={
            2023: TableDetectionResult(
                detected_pages=[
                    DetectedPage(year=2023, page_number=10, tables_detected=1),
                ],
                total_pages_processed=100,
            ),
            2024: TableDetectionResult(
                detected_pages=[
                    DetectedPage(year=2024, page_number=20, tables_detected=1),
                    DetectedPage(year=2024, page_number=25, tables_detected=1),
                ],
                total_pages_processed=132,
            ),
        },
    )

    updated_context = classifier.classify_tables_for_context(context)

    assert updated_context is context
    assert set(context.classification_results) == {2023, 2024}
    assert context.classification_results[2023].model_dump() == {
        "page_table_types": [
            {
                "year": 2023,
                "page_number": 10,
                "table_types": ["balance_sheet"],
            }
        ],
        "failed_pages": [],
    }
    assert context.classification_results[2024].model_dump() == {
        "page_table_types": [
            {
                "year": 2024,
                "page_number": 20,
                "table_types": ["income_statement"],
            },
            {
                "year": 2024,
                "page_number": 25,
                "table_types": ["cash_flow_statement"],
            },
        ],
        "failed_pages": [],
    }
    assert (
        context.classification_results[2023]
        is not context.classification_results[2024]
    )
    assert documents["reports/MLCF_2023.pdf"].closed is True
    assert documents["reports/MLCF_2024.pdf"].closed is True


def test_classify_tables_for_context_requires_detection_result_per_year() -> None:
    classifier = OpenAITableClassifier(
        client=FakeOpenAIClient([]),
        api_key="test_key",
        pdf_loader=lambda _: FakeDocument({}),
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

    with pytest.raises(ValueError, match="Missing table detection result"):
        classifier.classify_tables_for_context(context)


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
        request_timeout_seconds=15.0,
        sleep=lambda _: None,
    )

    result = classifier.classify_tables(
        pdf_path="annual_report.pdf",
        table_detection_result=TableDetectionResult(
            detected_pages=[
                DetectedPage(year=2024, page_number=20, tables_detected=1)
            ],
            total_pages_processed=30,
        ),
    )

    assert result.page_table_types[0].table_types == ["cash_flow_statement"]
    assert len(client.responses.calls) == 2
    assert client.responses.calls[0]["timeout"] == 15.0
    assert client.responses.calls[1]["timeout"] == 15.0


def test_classify_tables_records_page_failure_after_retry_exhaustion() -> None:
    classifier = OpenAITableClassifier(
        client=FakeOpenAIClient([RuntimeError("failure")]),
        api_key="test_key",
        pdf_loader=lambda _: FakeDocument({20: "Balance Sheet"}),
        max_retries=1,
    )

    result = classifier.classify_tables(
        pdf_path="annual_report.pdf",
        table_detection_result=TableDetectionResult(
            detected_pages=[
                DetectedPage(year=2024, page_number=20, tables_detected=1)
            ],
            total_pages_processed=30,
        ),
    )

    assert result.page_table_types == []
    assert result.failed_pages[0].page_number == 20
    assert "OpenAI table classification failed" in (
        result.failed_pages[0].error_message
    )


def test_classify_tables_retries_empty_and_malformed_openai_response() -> None:
    classifier = OpenAITableClassifier(
        client=FakeOpenAIClient(
            [
                FakeTextResponse(""),
                FakeTextResponse("{"),
                FakeResponse({"table_types": ["balance_sheet"]}),
            ]
        ),
        api_key="test_key",
        pdf_loader=lambda _: FakeDocument({20: "Balance Sheet"}),
        max_retries=3,
        retry_backoff_seconds=0,
        sleep=lambda _: None,
    )

    result = classifier.classify_tables(
        pdf_path="annual_report.pdf",
        table_detection_result=TableDetectionResult(
            detected_pages=[
                DetectedPage(year=2024, page_number=20, tables_detected=1)
            ],
            total_pages_processed=30,
        ),
    )

    assert result.page_table_types[0].table_types == ["balance_sheet"]
    assert result.failed_pages == []
    assert len(classifier._client.responses.calls) == 3


def test_classify_tables_retries_empty_string_labels() -> None:
    classifier = OpenAITableClassifier(
        client=FakeOpenAIClient(
            [
                FakeResponse({"table_types": [""]}),
                FakeResponse({"table_types": ["income_statement"]}),
            ]
        ),
        api_key="test_key",
        pdf_loader=lambda _: FakeDocument({20: "Income Statement"}),
        max_retries=2,
        retry_backoff_seconds=0,
        sleep=lambda _: None,
    )

    result = classifier.classify_tables(
        pdf_path="annual_report.pdf",
        table_detection_result=TableDetectionResult(
            detected_pages=[
                DetectedPage(year=2024, page_number=20, tables_detected=1)
            ],
            total_pages_processed=30,
        ),
    )

    assert (
        OpenAITableClassifier._RESPONSE_FORMAT["schema"]["properties"][
            "table_types"
        ]["items"]["minLength"]
        == 1
    )
    assert result.page_table_types[0].table_types == ["income_statement"]
    assert result.failed_pages == []
    assert len(classifier._client.responses.calls) == 2


def test_classify_tables_does_not_retry_terminal_4xx_errors() -> None:
    client = FakeOpenAIClient([FakeTerminalOpenAIError("bad request")])
    classifier = OpenAITableClassifier(
        client=client,
        api_key="test_key",
        pdf_loader=lambda _: FakeDocument({20: "Balance Sheet"}),
        max_retries=3,
        retry_backoff_seconds=0,
        sleep=lambda _: None,
    )

    result = classifier.classify_tables(
        pdf_path="annual_report.pdf",
        table_detection_result=TableDetectionResult(
            detected_pages=[
                DetectedPage(year=2024, page_number=20, tables_detected=1)
            ],
            total_pages_processed=30,
        ),
    )

    assert len(client.responses.calls) == 1
    assert result.page_table_types == []
    assert result.failed_pages[0].page_number == 20
    assert "terminal client error" in result.failed_pages[0].error_message


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
                "year": 2024,
                "page_number": 25,
                "table_types": ["income_statement"],
            }
        ],
        "failed_pages": [
            {
                "year": 2024,
                "page_number": 20,
                "error_message": "page not readable",
            }
        ],
    }
    assert "Classifying tables on page 20" in caplog.text
    assert "Page skipped due to classification error" in caplog.text
    assert "Table classification complete" in caplog.text


def test_classify_tables_isolates_page_level_openai_failures() -> None:
    client = FakeOpenAIClient(
        [
            RuntimeError("temporary OpenAI outage"),
            FakeResponse({"table_types": ["income_statement"]}),
        ]
    )
    classifier = OpenAITableClassifier(
        client=client,
        api_key="test_key",
        pdf_loader=lambda _: FakeDocument(
            {
                20: "Balance Sheet",
                25: "Income Statement",
            }
        ),
        max_retries=1,
    )

    result = classifier.classify_tables(
        pdf_path="annual_report.pdf",
        table_detection_result=_detection_result(),
    )

    assert result.model_dump() == {
        "page_table_types": [
            {
                "year": 2024,
                "page_number": 25,
                "table_types": ["income_statement"],
            }
        ],
        "failed_pages": [
            {
                "year": 2024,
                "page_number": 20,
                "error_message": (
                    "OpenAI table classification failed for page 20."
                ),
            }
        ],
    }
