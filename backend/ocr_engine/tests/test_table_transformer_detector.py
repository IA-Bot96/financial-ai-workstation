"""Unit tests for the Table Transformer detector service."""

import logging
import sys
from pathlib import Path

import pytest

BACKEND_DIR = Path(__file__).resolve().parents[2]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from ocr_engine.constants.detection_constants import (
    TABLE_DETECTION_CONFIDENCE_THRESHOLD,
    TABLE_DETECTION_MODEL_NAME,
)
from ocr_engine.services.interfaces.table_detector import ITableDetector
from ocr_engine.services.table_transformer_detector import TableTransformerDetector
from shared.models.company_context import CompanyContext
from shared.models.report import Report


class FakeImage:
    size = (100, 200)


class FakeDocument:
    def __init__(self, page_count: int) -> None:
        self.page_count = page_count
        self.closed = False

    def __len__(self) -> int:
        return self.page_count

    def close(self) -> None:
        self.closed = True


class FakeProcessor:
    def __init__(self, detections: list[dict[str, list[float]]]) -> None:
        self._detections = detections
        self.thresholds: list[float] = []

    def __call__(self, *, images: FakeImage, return_tensors: str) -> dict[str, str]:
        assert return_tensors == "pt"
        return {"pixel_values": "fake_tensor"}

    def post_process_object_detection(
        self,
        outputs: object,
        threshold: float,
        target_sizes: object,
    ) -> list[dict[str, list[float]]]:
        self.thresholds.append(threshold)
        return [self._detections.pop(0)]


class FakeModel:
    def __init__(self) -> None:
        self.eval_called = False

    def eval(self) -> None:
        self.eval_called = True

    def __call__(self, **inputs: str) -> object:
        return object()


class FakeTorch:
    class cuda:
        @staticmethod
        def is_available() -> bool:
            return False

    class _NoGrad:
        def __enter__(self) -> None:
            return None

        def __exit__(self, exc_type: object, exc: object, tb: object) -> None:
            return None

    def no_grad(self) -> _NoGrad:
        return self._NoGrad()

    def tensor(self, value: object, device: str | None = None) -> object:
        return {"value": value, "device": device}


def test_detection_constants_are_configurable_defaults() -> None:
    assert TABLE_DETECTION_CONFIDENCE_THRESHOLD == 0.90
    assert TABLE_DETECTION_MODEL_NAME == "microsoft/table-transformer-detection"


def test_table_transformer_detector_implements_interface() -> None:
    detector = TableTransformerDetector(
        processor=FakeProcessor([{"scores": []}]),
        model=FakeModel(),
        pdf_loader=lambda _: FakeDocument(1),
        page_renderer=lambda document, page_index: FakeImage(),
        torch_module=FakeTorch(),
    )

    assert isinstance(detector, ITableDetector)


def test_table_transformer_detector_rejects_invalid_threshold() -> None:
    with pytest.raises(ValueError, match="confidence_threshold"):
        TableTransformerDetector(
            processor=FakeProcessor([{"scores": []}]),
            model=FakeModel(),
            confidence_threshold=1.1,
            torch_module=FakeTorch(),
        )


def test_table_transformer_detector_requires_processor_and_model_pair() -> None:
    with pytest.raises(ValueError, match="processor and model"):
        TableTransformerDetector(
            processor=FakeProcessor([{"scores": []}]),
            model=None,
            torch_module=FakeTorch(),
        )


def test_detect_tables_returns_pages_with_detections_without_duplicates() -> None:
    document = FakeDocument(3)
    processor = FakeProcessor(
        [
            {"scores": [0.96]},
            {"scores": []},
            {"scores": [0.91, 0.92]},
        ]
    )

    detector = TableTransformerDetector(
        processor=processor,
        model=FakeModel(),
        pdf_loader=lambda _: document,
        page_renderer=lambda document, page_index: FakeImage(),
        confidence_threshold=0.93,
        torch_module=FakeTorch(),
    )

    result = detector.detect_tables("annual_report.pdf", year=2024)

    assert result.model_dump() == {
        "detected_pages": [
            {
                "year": 2024,
                "page_number": 1,
                "tables_detected": 1,
            },
            {
                "year": 2024,
                "page_number": 3,
                "tables_detected": 2,
            },
        ],
        "total_pages_processed": 3,
    }
    assert processor.thresholds == [0.93, 0.93, 0.93]
    assert document.closed is True


def test_detect_tables_for_context_stores_results_by_report_year() -> None:
    documents = {
        "reports/MLCF_2023.pdf": FakeDocument(2),
        "reports/MLCF_2024.pdf": FakeDocument(1),
    }
    processor = FakeProcessor(
        [
            {"scores": [0.96]},
            {"scores": []},
            {"scores": [0.91, 0.92]},
        ]
    )

    detector = TableTransformerDetector(
        processor=processor,
        model=FakeModel(),
        pdf_loader=lambda pdf_path: documents[pdf_path],
        page_renderer=lambda document, page_index: FakeImage(),
        torch_module=FakeTorch(),
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
    )

    updated_context = detector.detect_tables_for_context(context)

    assert updated_context is context
    assert set(context.table_detection_results) == {2023, 2024}
    assert context.table_detection_results[2023].model_dump() == {
        "detected_pages": [
            {
                "year": 2023,
                "page_number": 1,
                "tables_detected": 1,
            }
        ],
        "total_pages_processed": 2,
    }
    assert context.table_detection_results[2024].model_dump() == {
        "detected_pages": [
            {
                "year": 2024,
                "page_number": 1,
                "tables_detected": 2,
            }
        ],
        "total_pages_processed": 1,
    }
    assert (
        context.table_detection_results[2023]
        is not context.table_detection_results[2024]
    )
    assert documents["reports/MLCF_2023.pdf"].closed is True
    assert documents["reports/MLCF_2024.pdf"].closed is True


def test_detect_tables_skips_corrupted_pages_and_continues(
    caplog: pytest.LogCaptureFixture,
) -> None:
    processor = FakeProcessor(
        [
            {"scores": [0.96]},
            {"scores": [0.95]},
        ]
    )

    def render_page(document: FakeDocument, page_index: int) -> FakeImage:
        if page_index == 1:
            raise RuntimeError("corrupted page")
        return FakeImage()

    detector = TableTransformerDetector(
        processor=processor,
        model=FakeModel(),
        pdf_loader=lambda _: FakeDocument(3),
        page_renderer=render_page,
        torch_module=FakeTorch(),
    )

    with caplog.at_level(logging.INFO):
        result = detector.detect_tables("annual_report.pdf", year=2024)

    assert result.model_dump()["detected_pages"] == [
        {
            "year": 2024,
            "page_number": 1,
            "tables_detected": 1,
        },
        {
            "year": 2024,
            "page_number": 3,
            "tables_detected": 1,
        },
    ]
    assert result.total_pages_processed == 3
    assert "Processing page 1/3" in caplog.text
    assert "Tables detected on page 1" in caplog.text
    assert "Page skipped due to error" in caplog.text
    assert "Detection complete" in caplog.text


def test_detect_tables_raises_when_pdf_cannot_be_opened() -> None:
    detector = TableTransformerDetector(
        processor=FakeProcessor([]),
        model=FakeModel(),
        pdf_loader=lambda _: (_ for _ in ()).throw(FileNotFoundError("missing")),
        page_renderer=lambda document, page_index: FakeImage(),
        torch_module=FakeTorch(),
    )

    with pytest.raises(FileNotFoundError):
        detector.detect_tables("missing.pdf", year=2024)
