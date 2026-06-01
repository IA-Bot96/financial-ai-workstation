"""Proof of concept: compare page-level and detection-bbox table extraction.

This experiment is intentionally outside the production OCR pipeline. It uses
Table Transformer detections to crop detected table regions, extracts each crop
independently, and compares the result against the current full-page extraction
path for high-impact classification/extraction mismatch pages.
"""

from __future__ import annotations

import argparse
import csv
import json
import logging
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Iterable, Sequence

BACKEND_DIR = Path(__file__).resolve().parents[1] / "backend"
EXPERIMENTS_DIR = Path(__file__).resolve().parent
for path in (BACKEND_DIR, EXPERIMENTS_DIR):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from bbox_guided_extraction_experiment import (  # noqa: E402
    DEFAULT_BBOX_PADDING_POINTS,
    DEFAULT_CONFIDENCE_THRESHOLD,
    DEFAULT_DPI,
    DEFAULT_MODEL_NAME,
    DetectionBox,
    _detect_tables,
    _load_detections_json,
)
from ocr_engine.models.financial_table_classification import (  # noqa: E402
    FinancialTableClassificationResult,
    PageTableType,
)
from ocr_engine.models.table_detection_result import TableDetectionResult  # noqa: E402
from ocr_engine.services.camelot_table_extractor import (  # noqa: E402
    CamelotTableExtractor,
    UNCLASSIFIED_TABLE_TYPE,
)

TOP_MISMATCH_PAGES = [164, 163, 162, 271, 321, 356, 324, 353, 322, 328]
PDFPLUMBER_TEXT_SETTINGS = {
    "vertical_strategy": "text",
    "horizontal_strategy": "text",
}

logger = logging.getLogger("bbox_extraction_poc")


@dataclass(frozen=True)
class BBoxExtractionAttempt:
    """One extraction attempt for one detected bbox."""

    detection_index: int
    strategy: str
    extraction_error: str | None
    tables: list[list[list[str]]]


@dataclass(frozen=True)
class SelectedBBoxTable:
    """Selected bbox table used in the bbox-level comparison."""

    detection_index: int
    strategy: str
    table_index_within_attempt: int
    rows: list[list[str]]
    quality_score: float
    metric_value_count: int


def main() -> int:
    """Run the bbox extraction proof of concept."""

    args = _parse_args()
    _configure_logging(args.log_level)

    pdf_path = Path(args.pdf).resolve()
    context_path = Path(args.context_json).resolve()
    output_dir = Path(args.output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    if not pdf_path.exists():
        raise FileNotFoundError(f"PDF not found: {pdf_path}")
    if not context_path.exists():
        raise FileNotFoundError(f"Context JSON not found: {context_path}")

    pages = _deduplicate_pages(args.pages or TOP_MISMATCH_PAGES)
    context_payload = json.loads(context_path.read_text(encoding="utf-8"))
    classification_result = FinancialTableClassificationResult.model_validate(
        context_payload["classification_results"][str(args.source_report_year)]
    )
    detection_result = TableDetectionResult.model_validate(
        context_payload["table_detection_results"][str(args.source_report_year)]
    )
    page_classifications = {
        page_table_type.page_number: page_table_type
        for page_table_type in classification_result.page_table_types
    }
    production_detected_counts = {
        detected_page.page_number: detected_page.tables_detected
        for detected_page in detection_result.detected_pages
    }

    detections_by_page = _load_or_detect_tables(
        pdf_path=pdf_path,
        pages=pages,
        output_dir=output_dir,
        model_name=args.model_name,
        confidence_threshold=args.confidence_threshold,
        dpi=args.dpi,
        bbox_padding_points=args.bbox_padding_points,
        detections_json=Path(args.detections_json).resolve()
        if args.detections_json
        else None,
        keep_images=args.keep_images,
    )

    extractor = CamelotTableExtractor()
    page_reports: list[dict[str, Any]] = []
    for page_number in pages:
        page_table_type = page_classifications.get(page_number)
        if page_table_type is None:
            raise ValueError(f"No classification result found for page {page_number}.")

        page_reports.append(
            _compare_page(
                pdf_path=pdf_path,
                output_dir=output_dir,
                extractor=extractor,
                page_table_type=page_table_type,
                production_detected_count=production_detected_counts.get(
                    page_number,
                    0,
                ),
                detections=detections_by_page.get(page_number, []),
            )
        )

    report = _build_report(
        pdf_path=pdf_path,
        context_path=context_path,
        pages=pages,
        source_report_year=args.source_report_year,
        confidence_threshold=args.confidence_threshold,
        dpi=args.dpi,
        bbox_padding_points=args.bbox_padding_points,
        page_reports=page_reports,
    )
    report_path = output_dir / "bbox_extraction_poc.json"
    report_path.write_text(
        json.dumps(report, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    _write_summary_csv(output_dir / "bbox_extraction_poc_summary.csv", page_reports)

    print(json.dumps(report["summary"], indent=2))
    print(f"Report written to: {report_path}")
    return 0


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Compare current page-level table extraction with detection-bbox "
            "extraction for high-impact mismatch pages."
        )
    )
    parser.add_argument("--pdf", "--pdf-path", dest="pdf", required=True)
    parser.add_argument(
        "--context-json",
        default="output/lucky-cement_insights_diagnostics_context.json",
        help="Pipeline context JSON containing detection and classification outputs.",
    )
    parser.add_argument(
        "--source-report-year",
        type=int,
        default=2025,
        help="Report year key to read from the context JSON.",
    )
    parser.add_argument(
        "--pages",
        nargs="+",
        type=int,
        default=TOP_MISMATCH_PAGES,
        help=f"One-based PDF pages to test. Defaults to {TOP_MISMATCH_PAGES}.",
    )
    parser.add_argument(
        "--output-dir",
        default="output/bbox_extraction_poc",
        help="Directory for bbox_extraction_poc.json and CSV artifacts.",
    )
    parser.add_argument("--model-name", default=DEFAULT_MODEL_NAME)
    parser.add_argument(
        "--confidence-threshold",
        type=float,
        default=DEFAULT_CONFIDENCE_THRESHOLD,
    )
    parser.add_argument("--dpi", type=int, default=DEFAULT_DPI)
    parser.add_argument(
        "--bbox-padding-points",
        type=float,
        default=DEFAULT_BBOX_PADDING_POINTS,
    )
    parser.add_argument(
        "--detections-json",
        help="Optional detections.json to reuse instead of running Table Transformer.",
    )
    parser.add_argument("--keep-images", action="store_true")
    parser.add_argument(
        "--log-level",
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
    )
    return parser.parse_args()


def _configure_logging(level: str) -> None:
    logging.basicConfig(
        level=getattr(logging, level.upper()),
        format="%(levelname)s %(name)s: %(message)s",
    )


def _load_or_detect_tables(
    *,
    pdf_path: Path,
    pages: Sequence[int],
    output_dir: Path,
    model_name: str,
    confidence_threshold: float,
    dpi: int,
    bbox_padding_points: float,
    detections_json: Path | None,
    keep_images: bool,
) -> dict[int, list[DetectionBox]]:
    if detections_json is not None:
        return _load_detections_json(detections_json)
    return _detect_tables(
        pdf_path=pdf_path,
        pages=pages,
        output_dir=output_dir,
        model_name=model_name,
        confidence_threshold=confidence_threshold,
        dpi=dpi,
        bbox_padding_points=bbox_padding_points,
        keep_images=keep_images,
    )


def _compare_page(
    *,
    pdf_path: Path,
    output_dir: Path,
    extractor: CamelotTableExtractor,
    page_table_type: PageTableType,
    production_detected_count: int,
    detections: Sequence[DetectionBox],
) -> dict[str, Any]:
    page_number = page_table_type.page_number
    current_raw = extractor._extract_page_tables(str(pdf_path), page_number)
    current_tables, current_diagnostic = extractor._build_extracted_tables(
        page_table_type=page_table_type,
        raw_tables=current_raw.raw_tables,
        detected_table_count=production_detected_count,
        extraction_strategy=current_raw.strategy,
        extraction_quality=current_raw.quality,
    )

    attempts: list[dict[str, Any]] = []
    selected_bbox_tables: list[SelectedBBoxTable] = []
    for detection in detections:
        bbox_attempts = _extract_detection_bbox(
            pdf_path=pdf_path,
            page_number=page_number,
            detection=detection,
        )
        attempts.extend(
            _attempt_summary(
                attempt=attempt,
                extractor=extractor,
                page_number=page_number,
                output_dir=output_dir,
            )
            for attempt in bbox_attempts
        )
        selected_bbox_tables.extend(
            _select_best_tables_for_detection(
                attempts=bbox_attempts,
                extractor=extractor,
                source_report_year=page_table_type.year,
                page_number=page_number,
            )
        )

    bbox_raw_tables = [selected.rows for selected in selected_bbox_tables]
    bbox_quality = extractor._raw_extraction_result(
        strategy="bbox_selected_best",
        raw_tables=bbox_raw_tables,
    ).quality
    bbox_tables, bbox_diagnostic = extractor._build_extracted_tables(
        page_table_type=page_table_type,
        raw_tables=bbox_raw_tables,
        detected_table_count=len(detections),
        extraction_strategy="bbox_selected_best",
        extraction_quality=bbox_quality,
    )

    current_gap = max(
        0,
        current_diagnostic.classified_table_count
        - current_diagnostic.extracted_table_count,
    )
    bbox_gap = max(
        0,
        bbox_diagnostic.classified_table_count
        - bbox_diagnostic.extracted_table_count,
    )

    return {
        "page_number": page_number,
        "classified_table_types": list(page_table_type.table_types),
        "production_detected_table_count": production_detected_count,
        "poc_detected_bbox_count": len(detections),
        "detections": [asdict(detection) for detection in detections],
        "current_page_level": _diagnostic_summary(
            diagnostic=current_diagnostic,
            tables=current_tables,
            raw_tables=current_raw.raw_tables,
        ),
        "bbox_level": {
            **_diagnostic_summary(
                diagnostic=bbox_diagnostic,
                tables=bbox_tables,
                raw_tables=bbox_raw_tables,
            ),
            "selected_tables": [
                _selected_table_summary(selected, index)
                for index, selected in enumerate(selected_bbox_tables)
            ],
            "attempts": attempts,
        },
        "gap_reduction": {
            "classified_minus_extracted_before": current_gap,
            "classified_minus_extracted_after": bbox_gap,
            "absolute_reduction": current_gap - bbox_gap,
            "improved": bbox_gap < current_gap,
        },
    }


def _extract_detection_bbox(
    *,
    pdf_path: Path,
    page_number: int,
    detection: DetectionBox,
) -> list[BBoxExtractionAttempt]:
    return [
        _extract_pdfplumber_bbox_text(
            pdf_path=pdf_path,
            page_number=page_number,
            detection=detection,
        ),
        _extract_camelot_bbox(
            pdf_path=pdf_path,
            page_number=page_number,
            detection=detection,
            flavor="stream",
        ),
        _extract_camelot_bbox(
            pdf_path=pdf_path,
            page_number=page_number,
            detection=detection,
            flavor="lattice",
        ),
    ]


def _extract_pdfplumber_bbox_text(
    *,
    pdf_path: Path,
    page_number: int,
    detection: DetectionBox,
) -> BBoxExtractionAttempt:
    try:
        import pdfplumber

        with pdfplumber.open(pdf_path) as pdf:
            page = pdf.pages[page_number - 1]
            cropped = page.crop(tuple(detection.pdf_bbox_top_left))
            tables = (
                cropped.extract_tables(table_settings=PDFPLUMBER_TEXT_SETTINGS) or []
            )
        return BBoxExtractionAttempt(
            detection_index=detection.table_index,
            strategy="bbox_pdfplumber_text",
            extraction_error=None,
            tables=[
                CamelotTableExtractor._normalize_rows(table)
                for table in tables
                if table
            ],
        )
    except Exception as exc:
        logger.exception(
            "pdfplumber bbox extraction failed",
            extra={"page": page_number, "detection_index": detection.table_index},
        )
        return BBoxExtractionAttempt(
            detection_index=detection.table_index,
            strategy="bbox_pdfplumber_text",
            extraction_error=_error_message(exc),
            tables=[],
        )


def _extract_camelot_bbox(
    *,
    pdf_path: Path,
    page_number: int,
    detection: DetectionBox,
    flavor: str,
) -> BBoxExtractionAttempt:
    strategy = f"bbox_camelot_{flavor}"
    try:
        import camelot

        tables = camelot.read_pdf(
            str(pdf_path),
            pages=str(page_number),
            flavor=flavor,
            table_areas=[detection.camelot_table_area],
        )
        return BBoxExtractionAttempt(
            detection_index=detection.table_index,
            strategy=strategy,
            extraction_error=None,
            tables=[
                CamelotTableExtractor._normalize_rows(table.df.values.tolist())
                for table in tables
                if hasattr(table, "df")
            ],
        )
    except Exception as exc:
        logger.exception(
            "Camelot bbox extraction failed",
            extra={
                "page": page_number,
                "detection_index": detection.table_index,
                "flavor": flavor,
            },
        )
        return BBoxExtractionAttempt(
            detection_index=detection.table_index,
            strategy=strategy,
            extraction_error=_error_message(exc),
            tables=[],
        )


def _select_best_tables_for_detection(
    *,
    attempts: Sequence[BBoxExtractionAttempt],
    extractor: CamelotTableExtractor,
    source_report_year: int,
    page_number: int,
) -> list[SelectedBBoxTable]:
    best_attempt = max(
        attempts,
        key=lambda attempt: _attempt_quality_tuple(
            attempt=attempt,
            extractor=extractor,
            source_report_year=source_report_year,
            page_number=page_number,
        ),
        default=None,
    )
    if best_attempt is None:
        return []

    selected: list[SelectedBBoxTable] = []
    for table_index, rows in enumerate(best_attempt.tables):
        metric_values = extractor._extract_metric_values(
            rows=rows,
            source_report_year=source_report_year,
            page_number=page_number,
            table_type=best_attempt.strategy,
        )
        selected.append(
            SelectedBBoxTable(
                detection_index=best_attempt.detection_index,
                strategy=best_attempt.strategy,
                table_index_within_attempt=table_index,
                rows=rows,
                quality_score=_quality_score(extractor, rows, len(metric_values)),
                metric_value_count=len(metric_values),
            )
        )
    return selected


def _attempt_quality_tuple(
    *,
    attempt: BBoxExtractionAttempt,
    extractor: CamelotTableExtractor,
    source_report_year: int,
    page_number: int,
) -> tuple[int, float, int, int]:
    metric_values = 0
    quality_scores: list[float] = []
    for rows in attempt.tables:
        values = extractor._extract_metric_values(
            rows=rows,
            source_report_year=source_report_year,
            page_number=page_number,
            table_type=attempt.strategy,
        )
        metric_values += len(values)
        quality_scores.append(_quality_score(extractor, rows, len(values)))
    return (
        metric_values,
        max(quality_scores, default=0.0),
        len(attempt.tables),
        -_strategy_rank(attempt.strategy),
    )


def _strategy_rank(strategy: str) -> int:
    order = {
        "bbox_pdfplumber_text": 0,
        "bbox_camelot_stream": 1,
        "bbox_camelot_lattice": 2,
    }
    return order.get(strategy, 99)


def _attempt_summary(
    *,
    attempt: BBoxExtractionAttempt,
    extractor: CamelotTableExtractor,
    page_number: int,
    output_dir: Path,
) -> dict[str, Any]:
    table_summaries: list[dict[str, Any]] = []
    for table_index, rows in enumerate(attempt.tables):
        metric_values = extractor._extract_metric_values(
            rows=rows,
            source_report_year=9999,
            page_number=page_number,
            table_type=attempt.strategy,
        )
        csv_path = _write_table_csv(
            output_dir=output_dir,
            page_number=page_number,
            detection_index=attempt.detection_index,
            strategy=attempt.strategy,
            table_index=table_index,
            rows=rows,
        )
        table_summaries.append(
            {
                "table_index": table_index,
                "row_count": len(rows),
                "column_count": _column_count(rows),
                "metric_value_count": len(metric_values),
                "quality_score": _quality_score(extractor, rows, len(metric_values)),
                "text_sample": _text_sample(rows),
                "csv_path": str(csv_path),
            }
        )
    return {
        "detection_index": attempt.detection_index,
        "strategy": attempt.strategy,
        "extraction_error": attempt.extraction_error,
        "extracted_table_count": len(attempt.tables),
        "metric_value_count": sum(
            table["metric_value_count"] for table in table_summaries
        ),
        "best_quality_score": max(
            (table["quality_score"] for table in table_summaries),
            default=0.0,
        ),
        "tables": table_summaries,
    }


def _selected_table_summary(
    selected: SelectedBBoxTable,
    selected_index: int,
) -> dict[str, Any]:
    return {
        "selected_index": selected_index,
        "detection_index": selected.detection_index,
        "strategy": selected.strategy,
        "table_index_within_attempt": selected.table_index_within_attempt,
        "row_count": len(selected.rows),
        "column_count": _column_count(selected.rows),
        "metric_value_count": selected.metric_value_count,
        "quality_score": selected.quality_score,
        "text_sample": _text_sample(selected.rows),
    }


def _diagnostic_summary(
    *,
    diagnostic: Any,
    tables: Sequence[Any],
    raw_tables: Sequence[Sequence[Sequence[str]]],
) -> dict[str, Any]:
    return {
        "detected_table_count": diagnostic.detected_table_count,
        "classified_table_count": diagnostic.classified_table_count,
        "extracted_table_count": diagnostic.extracted_table_count,
        "matched_table_count": diagnostic.matched_table_count,
        "unclassified_table_count": sum(
            1 for table in tables if table.table_type == UNCLASSIFIED_TABLE_TYPE
        ),
        "metric_values_generated": sum(len(table.metric_values) for table in tables),
        "unmatched_classifications": list(diagnostic.unmatched_classifications),
        "unmatched_extractions": list(diagnostic.unmatched_extractions),
        "assigned_tables": [
            {
                "table_index": table.table_index,
                "table_type": table.table_type,
                "row_count": len(table.rows),
                "column_count": _column_count(table.rows),
                "metric_value_count": len(table.metric_values),
            }
            for table in tables
        ],
        "raw_tables": [
            {
                "raw_table_index": index,
                "row_count": len(rows),
                "column_count": _column_count(rows),
                "text_sample": _text_sample(rows),
            }
            for index, rows in enumerate(raw_tables)
        ],
    }


def _build_report(
    *,
    pdf_path: Path,
    context_path: Path,
    pages: Sequence[int],
    source_report_year: int,
    confidence_threshold: float,
    dpi: int,
    bbox_padding_points: float,
    page_reports: Sequence[dict[str, Any]],
) -> dict[str, Any]:
    current = [_page_level(page, "current_page_level") for page in page_reports]
    bbox = [_page_level(page, "bbox_level") for page in page_reports]
    current_gap = sum(
        max(0, item["classified_table_count"] - item["extracted_table_count"])
        for item in current
    )
    bbox_gap = sum(
        max(0, item["classified_table_count"] - item["extracted_table_count"])
        for item in bbox
    )
    return {
        "pdf_path": str(pdf_path),
        "context_json": str(context_path),
        "source_report_year": source_report_year,
        "pages": list(pages),
        "experiment": {
            "purpose": (
                "Validate whether extraction per detected table bbox reduces "
                "classified_table_count > extracted_table_count mismatch."
            ),
            "detection_model": DEFAULT_MODEL_NAME,
            "confidence_threshold": confidence_threshold,
            "dpi": dpi,
            "bbox_padding_points": bbox_padding_points,
            "bbox_strategies": [
                "bbox_pdfplumber_text",
                "bbox_camelot_stream",
                "bbox_camelot_lattice",
            ],
            "selection_rule": (
                "For each detected bbox, select the strategy with the most "
                "MetricValues, then highest quality score, then most tables."
            ),
        },
        "summary": {
            "pages_processed": len(page_reports),
            "detected_bboxes": sum(page["poc_detected_bbox_count"] for page in page_reports),
            "current_page_level": _aggregate(current),
            "bbox_level": _aggregate(bbox),
            "classified_minus_extracted_gap_before": current_gap,
            "classified_minus_extracted_gap_after": bbox_gap,
            "gap_reduction": current_gap - bbox_gap,
            "pages_improved": sum(
                1 for page in page_reports if page["gap_reduction"]["improved"]
            ),
            "metric_value_delta": (
                sum(item["metric_values_generated"] for item in bbox)
                - sum(item["metric_values_generated"] for item in current)
            ),
        },
        "page_results": list(page_reports),
    }


def _page_level(page: dict[str, Any], key: str) -> dict[str, Any]:
    return page[key]


def _aggregate(items: Sequence[dict[str, Any]]) -> dict[str, Any]:
    return {
        "extracted_table_count": sum(item["extracted_table_count"] for item in items),
        "matched_table_count": sum(item["matched_table_count"] for item in items),
        "unclassified_tables": sum(item["unclassified_table_count"] for item in items),
        "metric_values_generated": sum(
            item["metric_values_generated"] for item in items
        ),
        "unmatched_classified_types": sum(
            len(item["unmatched_classifications"]) for item in items
        ),
    }


def _quality_score(
    extractor: CamelotTableExtractor,
    rows: Sequence[Sequence[str]],
    metric_value_count: int,
) -> float:
    _year_header_row, year_columns = extractor._find_year_columns(rows)
    metric_labels = sum(
        1 for row in rows if extractor._metric_label_index(row) is not None
    )
    score = 0.0
    if len(rows) >= 2:
        score += 15.0
    if _column_count(rows) >= 2:
        score += 15.0
    if year_columns:
        score += min(25.0, 12.5 * len(year_columns))
    if metric_labels:
        score += min(20.0, 2.0 * metric_labels)
    if metric_value_count:
        score += min(25.0, 2.5 * metric_value_count)
    return round(min(score, 100.0), 2)


def _write_summary_csv(path: Path, page_reports: Sequence[dict[str, Any]]) -> None:
    rows = []
    for page in page_reports:
        rows.append(
            {
                "page_number": page["page_number"],
                "classified_table_count": len(page["classified_table_types"]),
                "detected_bboxes": page["poc_detected_bbox_count"],
                "current_extracted": page["current_page_level"]["extracted_table_count"],
                "bbox_extracted": page["bbox_level"]["extracted_table_count"],
                "current_matched": page["current_page_level"]["matched_table_count"],
                "bbox_matched": page["bbox_level"]["matched_table_count"],
                "current_unclassified": page["current_page_level"]["unclassified_table_count"],
                "bbox_unclassified": page["bbox_level"]["unclassified_table_count"],
                "current_metric_values": page["current_page_level"]["metric_values_generated"],
                "bbox_metric_values": page["bbox_level"]["metric_values_generated"],
                "gap_before": page["gap_reduction"]["classified_minus_extracted_before"],
                "gap_after": page["gap_reduction"]["classified_minus_extracted_after"],
                "gap_reduction": page["gap_reduction"]["absolute_reduction"],
            }
        )
    with path.open("w", newline="", encoding="utf-8") as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=list(rows[0]) if rows else [])
        if rows:
            writer.writeheader()
            writer.writerows(rows)


def _write_table_csv(
    *,
    output_dir: Path,
    page_number: int,
    detection_index: int,
    strategy: str,
    table_index: int,
    rows: Sequence[Sequence[str]],
) -> Path:
    table_dir = output_dir / "tables"
    table_dir.mkdir(parents=True, exist_ok=True)
    path = (
        table_dir
        / f"page_{page_number:04d}_bbox_{detection_index:02d}_{strategy}_table_{table_index:02d}.csv"
    )
    with path.open("w", newline="", encoding="utf-8-sig") as csv_file:
        writer = csv.writer(csv_file)
        writer.writerows(rows)
    return path


def _text_sample(rows: Sequence[Sequence[str]], limit: int = 350) -> str:
    text = " | ".join(
        " ".join(str(cell).strip() for cell in row if str(cell).strip())
        for row in rows[:8]
    )
    return " ".join(text.split())[:limit]


def _column_count(rows: Sequence[Sequence[str]]) -> int:
    return max((len(row) for row in rows), default=0)


def _deduplicate_pages(pages: Iterable[int]) -> list[int]:
    seen: set[int] = set()
    deduplicated: list[int] = []
    for page in pages:
        if page <= 0:
            raise ValueError(f"Page numbers must be positive: {page}")
        if page in seen:
            continue
        seen.add(page)
        deduplicated.append(page)
    return deduplicated


def _error_message(exc: Exception) -> str:
    return str(exc) or exc.__class__.__name__


if __name__ == "__main__":
    raise SystemExit(main())
