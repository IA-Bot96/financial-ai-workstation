"""Experiment: compare bbox-guided and stream-mode table extraction.

This script is intentionally outside the production OCR pipeline. It preserves
Table Transformer detections, including bounding boxes, confidence, and labels,
then compares several extraction strategies on selected pages:

* full-page Camelot lattice
* detection-bbox Camelot lattice
* full-page Camelot stream
* detection-bbox Camelot stream
* full-page pdfplumber text strategies

The goal is to determine whether better table regions and extraction settings
recover year headers, metric labels, and MetricValue-compatible structures.
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
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from ocr_engine.services.camelot_table_extractor import CamelotTableExtractor


DEFAULT_MODEL_NAME = "microsoft/table-transformer-detection"
DEFAULT_CONFIDENCE_THRESHOLD = 0.90
DEFAULT_DPI = 144
DEFAULT_BBOX_PADDING_POINTS = 6.0
KNOWN_FAILURE_PAGES = [224, 225, 196, 102, 104, 190, 191, 289, 290, 291, 292]
PDFPLUMBER_TEXT_SETTINGS = {
    "vertical_strategy": "text",
    "horizontal_strategy": "text",
}

logger = logging.getLogger("bbox_guided_extraction_experiment")


@dataclass(frozen=True)
class DetectionBox:
    """Preserved table detection metadata for one table candidate."""

    page_number: int
    table_index: int
    label: str
    confidence: float
    image_bbox: list[float]
    pdf_bbox_top_left: list[float]
    camelot_table_area: str


@dataclass(frozen=True)
class ExtractionAttempt:
    """One strategy result for one page or detected bbox."""

    page_number: int
    strategy: str
    crop_table_index: int | None
    extraction_error: str | None
    tables: list[dict[str, Any]]


def main() -> int:
    """Run the bbox-guided extraction experiment."""

    args = _parse_args()
    _configure_logging(args.log_level)

    pdf_path = Path(args.pdf).resolve()
    output_dir = Path(args.output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    if not pdf_path.exists():
        raise FileNotFoundError(f"PDF not found: {pdf_path}")

    pages = _deduplicate_pages(args.pages or KNOWN_FAILURE_PAGES)
    logger.info("Starting extraction experiment", extra={"pages": pages})

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
        skip_detection=args.skip_detection,
        keep_images=args.keep_images,
    )

    _write_json(
        output_dir / "detections.json",
        {
            str(page): [asdict(detection) for detection in detections]
            for page, detections in detections_by_page.items()
        },
    )

    attempts: list[ExtractionAttempt] = []
    for page_number in pages:
        detections = detections_by_page.get(page_number, [])
        attempts.extend(
            _run_page_strategies(
                pdf_path=pdf_path,
                page_number=page_number,
                detections=detections,
                output_dir=output_dir,
            )
        )

    report = _build_report(
        pdf_path=pdf_path,
        pages=pages,
        detections_by_page=detections_by_page,
        attempts=attempts,
    )
    _write_json(output_dir / "extraction_experiment_report.json", report)
    _write_summary_csv(output_dir / "extraction_experiment_summary.csv", attempts)

    logger.info(
        "Extraction experiment complete",
        extra={
            "output_dir": str(output_dir),
            "pages": len(pages),
            "attempts": len(attempts),
        },
    )
    print(json.dumps(report["summary"], indent=2))
    print(f"Report written to: {output_dir / 'extraction_experiment_report.json'}")
    return 0


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Compare full-page, bbox-cropped, lattice, stream, and pdfplumber "
            "text-strategy table extraction."
        )
    )
    parser.add_argument(
        "--pdf",
        "--pdf-path",
        dest="pdf",
        required=True,
        help="Input annual report PDF path.",
    )
    parser.add_argument(
        "--pages",
        nargs="+",
        type=int,
        default=KNOWN_FAILURE_PAGES,
        help=(
            "One-based PDF pages to test. Defaults to known failure pages: "
            f"{KNOWN_FAILURE_PAGES}."
        ),
    )
    parser.add_argument(
        "--output-dir",
        default="output/bbox_extraction_experiment",
        help="Directory for JSON/CSV artifacts.",
    )
    parser.add_argument(
        "--model-name",
        default=DEFAULT_MODEL_NAME,
        help="Hugging Face table detection model name.",
    )
    parser.add_argument(
        "--confidence-threshold",
        type=float,
        default=DEFAULT_CONFIDENCE_THRESHOLD,
        help="Minimum detection confidence to preserve.",
    )
    parser.add_argument(
        "--dpi",
        type=int,
        default=DEFAULT_DPI,
        help="DPI used when rendering PDF pages for detection.",
    )
    parser.add_argument(
        "--bbox-padding-points",
        type=float,
        default=DEFAULT_BBOX_PADDING_POINTS,
        help="Padding applied around detected table boxes in PDF points.",
    )
    parser.add_argument(
        "--detections-json",
        help="Optional previously saved detections.json to reuse.",
    )
    parser.add_argument(
        "--skip-detection",
        action="store_true",
        help="Skip Table Transformer and run only full-page extraction strategies.",
    )
    parser.add_argument(
        "--keep-images",
        action="store_true",
        help="Save rendered page images used for detection.",
    )
    parser.add_argument(
        "--log-level",
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="Console logging level.",
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
    skip_detection: bool,
    keep_images: bool,
) -> dict[int, list[DetectionBox]]:
    if detections_json is not None:
        return _load_detections_json(detections_json)
    if skip_detection:
        return {page: [] for page in pages}
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


def _detect_tables(
    *,
    pdf_path: Path,
    pages: Sequence[int],
    output_dir: Path,
    model_name: str,
    confidence_threshold: float,
    dpi: int,
    bbox_padding_points: float,
    keep_images: bool,
) -> dict[int, list[DetectionBox]]:
    """Run Table Transformer and preserve bbox/confidence/label outputs."""

    try:
        import fitz
        import torch
        from PIL import Image
        from transformers import AutoImageProcessor
        from transformers import TableTransformerForObjectDetection
    except ImportError as exc:
        raise RuntimeError(
            "Table detection requires PyMuPDF, Pillow, torch, and transformers. "
            "Use --skip-detection or --detections-json to compare full-page "
            "strategies without running Table Transformer."
        ) from exc

    processor = AutoImageProcessor.from_pretrained(model_name)
    model = TableTransformerForObjectDetection.from_pretrained(model_name)
    device = "cuda" if torch.cuda.is_available() else "cpu"
    model.to(device)
    model.eval()

    image_dir = output_dir / "rendered_pages"
    if keep_images:
        image_dir.mkdir(parents=True, exist_ok=True)

    detections_by_page: dict[int, list[DetectionBox]] = {}
    zoom = dpi / 72
    matrix = fitz.Matrix(zoom, zoom)

    with fitz.open(pdf_path) as document:
        for page_number in pages:
            if page_number < 1 or page_number > len(document):
                raise ValueError(
                    f"Page {page_number} is outside PDF page range 1-{len(document)}."
                )

            page = document.load_page(page_number - 1)
            pixmap = page.get_pixmap(matrix=matrix, alpha=False)
            image = Image.frombytes(
                "RGB",
                (pixmap.width, pixmap.height),
                pixmap.samples,
            )
            if keep_images:
                image.save(image_dir / f"page_{page_number:04d}_{dpi}dpi.png")

            logger.info("Running table detection", extra={"page": page_number})
            inputs = processor(images=image, return_tensors="pt").to(device)
            with torch.no_grad():
                outputs = model(**inputs)

            processed = processor.post_process_object_detection(
                outputs,
                threshold=confidence_threshold,
                target_sizes=torch.tensor([image.size[::-1]], device=device),
            )
            page_detections = _detections_from_model_output(
                processed[0],
                page_number=page_number,
                page_width=float(page.rect.width),
                page_height=float(page.rect.height),
                zoom=zoom,
                padding_points=bbox_padding_points,
                id_to_label=getattr(model.config, "id2label", {}),
            )
            detections_by_page[page_number] = page_detections
            logger.info(
                "Detection outputs preserved",
                extra={"page": page_number, "detections": len(page_detections)},
            )

    return detections_by_page


def _detections_from_model_output(
    output: dict[str, Any],
    *,
    page_number: int,
    page_width: float,
    page_height: float,
    zoom: float,
    padding_points: float,
    id_to_label: dict[int, str],
) -> list[DetectionBox]:
    scores = _tensor_to_list(output.get("scores", []))
    labels = _tensor_to_list(output.get("labels", []))
    boxes = _tensor_to_list(output.get("boxes", []))

    detections: list[DetectionBox] = []
    for table_index, (score, label_id, image_bbox) in enumerate(
        zip(scores, labels, boxes)
    ):
        label_key = int(label_id)
        label = id_to_label.get(label_key, str(label_key))
        pdf_bbox = _image_bbox_to_pdf_top_left_bbox(
            image_bbox=image_bbox,
            page_width=page_width,
            page_height=page_height,
            zoom=zoom,
            padding_points=padding_points,
        )
        detections.append(
            DetectionBox(
                page_number=page_number,
                table_index=table_index,
                label=label,
                confidence=round(float(score), 6),
                image_bbox=[round(float(value), 3) for value in image_bbox],
                pdf_bbox_top_left=[round(value, 3) for value in pdf_bbox],
                camelot_table_area=_top_left_bbox_to_camelot_area(
                    pdf_bbox,
                    page_height=page_height,
                ),
            )
        )
    return detections


def _image_bbox_to_pdf_top_left_bbox(
    *,
    image_bbox: Sequence[float],
    page_width: float,
    page_height: float,
    zoom: float,
    padding_points: float,
) -> list[float]:
    x0, y0, x1, y1 = (float(value) for value in image_bbox)
    left = max(0.0, x0 / zoom - padding_points)
    top = max(0.0, y0 / zoom - padding_points)
    right = min(page_width, x1 / zoom + padding_points)
    bottom = min(page_height, y1 / zoom + padding_points)
    return [left, top, right, bottom]


def _top_left_bbox_to_camelot_area(
    top_left_bbox: Sequence[float],
    *,
    page_height: float,
) -> str:
    left, top, right, bottom = top_left_bbox
    camelot_top = page_height - top
    camelot_bottom = page_height - bottom
    return ",".join(
        _format_coord(value)
        for value in (left, camelot_top, right, camelot_bottom)
    )


def _run_page_strategies(
    *,
    pdf_path: Path,
    page_number: int,
    detections: Sequence[DetectionBox],
    output_dir: Path,
) -> list[ExtractionAttempt]:
    attempts = [
        _run_camelot_strategy(
            pdf_path=pdf_path,
            page_number=page_number,
            strategy="full_page_camelot_lattice",
            flavor="lattice",
            table_area=None,
            crop_table_index=None,
            output_dir=output_dir,
        ),
        _run_camelot_strategy(
            pdf_path=pdf_path,
            page_number=page_number,
            strategy="full_page_camelot_stream",
            flavor="stream",
            table_area=None,
            crop_table_index=None,
            output_dir=output_dir,
        ),
        _run_pdfplumber_text_strategy(
            pdf_path=pdf_path,
            page_number=page_number,
            output_dir=output_dir,
        ),
    ]

    for detection in detections:
        attempts.append(
            _run_camelot_strategy(
                pdf_path=pdf_path,
                page_number=page_number,
                strategy="cropped_bbox_camelot_lattice",
                flavor="lattice",
                table_area=detection.camelot_table_area,
                crop_table_index=detection.table_index,
                output_dir=output_dir,
            )
        )
        attempts.append(
            _run_camelot_strategy(
                pdf_path=pdf_path,
                page_number=page_number,
                strategy="cropped_bbox_camelot_stream",
                flavor="stream",
                table_area=detection.camelot_table_area,
                crop_table_index=detection.table_index,
                output_dir=output_dir,
            )
        )

    return attempts


def _run_camelot_strategy(
    *,
    pdf_path: Path,
    page_number: int,
    strategy: str,
    flavor: str,
    table_area: str | None,
    crop_table_index: int | None,
    output_dir: Path,
) -> ExtractionAttempt:
    kwargs: dict[str, Any] = {
        "pages": str(page_number),
        "flavor": flavor,
    }
    if table_area is not None:
        kwargs["table_areas"] = [table_area]

    try:
        import camelot

        tables = camelot.read_pdf(str(pdf_path), **kwargs)
        raw_tables = [
            CamelotTableExtractor._normalize_rows(table.df.values.tolist())
            for table in tables
            if hasattr(table, "df")
        ]
        table_results = _summarize_tables(
            page_number=page_number,
            strategy=strategy,
            crop_table_index=crop_table_index,
            raw_tables=[table for table in raw_tables if table],
            output_dir=output_dir,
        )
        return ExtractionAttempt(
            page_number=page_number,
            strategy=strategy,
            crop_table_index=crop_table_index,
            extraction_error=None,
            tables=table_results,
        )
    except Exception as exc:
        logger.exception(
            "Camelot strategy failed",
            extra={
                "page": page_number,
                "strategy": strategy,
                "flavor": flavor,
                "table_area": table_area,
            },
        )
        return ExtractionAttempt(
            page_number=page_number,
            strategy=strategy,
            crop_table_index=crop_table_index,
            extraction_error=_error_message(exc),
            tables=[],
        )


def _run_pdfplumber_text_strategy(
    *,
    pdf_path: Path,
    page_number: int,
    output_dir: Path,
) -> ExtractionAttempt:
    strategy = "full_page_pdfplumber_text"
    try:
        import pdfplumber

        with pdfplumber.open(pdf_path) as pdf:
            page = pdf.pages[page_number - 1]
            tables = page.extract_tables(table_settings=PDFPLUMBER_TEXT_SETTINGS) or []

        raw_tables = [CamelotTableExtractor._normalize_rows(table) for table in tables]
        table_results = _summarize_tables(
            page_number=page_number,
            strategy=strategy,
            crop_table_index=None,
            raw_tables=[table for table in raw_tables if table],
            output_dir=output_dir,
        )
        return ExtractionAttempt(
            page_number=page_number,
            strategy=strategy,
            crop_table_index=None,
            extraction_error=None,
            tables=table_results,
        )
    except Exception as exc:
        logger.exception(
            "pdfplumber text strategy failed",
            extra={"page": page_number, "strategy": strategy},
        )
        return ExtractionAttempt(
            page_number=page_number,
            strategy=strategy,
            crop_table_index=None,
            extraction_error=_error_message(exc),
            tables=[],
        )


def _summarize_tables(
    *,
    page_number: int,
    strategy: str,
    crop_table_index: int | None,
    raw_tables: list[list[list[str]]],
    output_dir: Path,
) -> list[dict[str, Any]]:
    helper = _metric_helper()
    tables: list[dict[str, Any]] = []
    table_dir = output_dir / "tables"
    table_dir.mkdir(parents=True, exist_ok=True)

    for extracted_table_index, rows in enumerate(raw_tables):
        year_header_row, year_columns = helper._find_year_columns(rows)
        metric_labels = _metric_labels(rows, helper)
        metric_values = helper._extract_metric_values(
            rows=rows,
            source_report_year=9999,
            page_number=page_number,
            table_type=strategy,
        )
        summary = {
            "page_number": page_number,
            "strategy": strategy,
            "crop_table_index": crop_table_index,
            "extracted_table_index": extracted_table_index,
            "row_count": len(rows),
            "column_count": _column_count(rows),
            "year_header_row": year_header_row,
            "detected_year_columns": {
                str(column_index): value_year
                for column_index, value_year in year_columns.items()
            },
            "detected_metric_labels": metric_labels[:50],
            "detected_metric_label_count": len(metric_labels),
            "metric_value_count": len(metric_values),
            "metric_values_extractable": bool(metric_values),
            "quality_score": _quality_score(
                rows=rows,
                year_columns=year_columns,
                metric_labels=metric_labels,
                metric_value_count=len(metric_values),
            ),
            "csv_path": "",
            "rows": rows,
        }
        csv_path = table_dir / _artifact_name(
            page_number=page_number,
            strategy=strategy,
            crop_table_index=crop_table_index,
            extracted_table_index=extracted_table_index,
            suffix=".csv",
        )
        _write_rows_csv(csv_path, rows)
        summary["csv_path"] = str(csv_path)
        tables.append(summary)

    return tables


def _metric_labels(
    rows: Sequence[Sequence[str]],
    helper: CamelotTableExtractor,
) -> list[dict[str, Any]]:
    labels: list[dict[str, Any]] = []
    for row_index, row in enumerate(rows):
        label_index = helper._metric_label_index(row)
        if label_index is None:
            continue
        labels.append(
            {
                "row_index": row_index,
                "column_index": label_index,
                "label": str(row[label_index]).strip(),
            }
        )
    return labels


def _quality_score(
    *,
    rows: Sequence[Sequence[str]],
    year_columns: dict[int, int],
    metric_labels: Sequence[dict[str, Any]],
    metric_value_count: int,
) -> float:
    """Score table usefulness for financial MetricValue extraction."""

    row_count = len(rows)
    column_count = _column_count(rows)
    non_empty_cells = sum(
        1 for row in rows for cell in row if str(cell).strip()
    )

    score = 0.0
    if row_count >= 2:
        score += 15.0
    if column_count >= 2:
        score += 15.0
    if non_empty_cells >= 4:
        score += 10.0
    if year_columns:
        score += min(25.0, 12.5 * len(year_columns))
    if metric_labels:
        score += min(20.0, 2.0 * len(metric_labels))
    if metric_value_count:
        score += min(15.0, 3.0 * metric_value_count)
    return round(min(score, 100.0), 2)


def _build_report(
    *,
    pdf_path: Path,
    pages: Sequence[int],
    detections_by_page: dict[int, list[DetectionBox]],
    attempts: Sequence[ExtractionAttempt],
) -> dict[str, Any]:
    summaries = [asdict(attempt) for attempt in attempts]
    best_by_page = {}
    for page_number in pages:
        page_attempts = [
            table
            for attempt in attempts
            if attempt.page_number == page_number
            for table in attempt.tables
        ]
        best_by_page[str(page_number)] = max(
            page_attempts,
            key=lambda table: table["quality_score"],
            default=None,
        )

    all_tables = [
        table for attempt in attempts for table in attempt.tables
    ]
    return {
        "pdf_path": str(pdf_path),
        "pages": list(pages),
        "strategies": [
            "full_page_camelot_lattice",
            "cropped_bbox_camelot_lattice",
            "full_page_camelot_stream",
            "cropped_bbox_camelot_stream",
            "full_page_pdfplumber_text",
        ],
        "pdfplumber_text_settings": PDFPLUMBER_TEXT_SETTINGS,
        "detections": {
            str(page): [asdict(detection) for detection in detections]
            for page, detections in detections_by_page.items()
        },
        "attempts": summaries,
        "best_table_by_page": best_by_page,
        "summary": {
            "pages_processed": len(pages),
            "detections_preserved": sum(
                len(detections) for detections in detections_by_page.values()
            ),
            "extraction_attempts": len(attempts),
            "tables_extracted": len(all_tables),
            "tables_with_year_columns": sum(
                1 for table in all_tables if table["detected_year_columns"]
            ),
            "tables_with_metric_labels": sum(
                1 for table in all_tables if table["detected_metric_label_count"] > 0
            ),
            "tables_with_metric_values": sum(
                1 for table in all_tables if table["metric_values_extractable"]
            ),
            "best_quality_score": max(
                (table["quality_score"] for table in all_tables),
                default=0.0,
            ),
        },
    }


def _write_summary_csv(path: Path, attempts: Sequence[ExtractionAttempt]) -> None:
    rows: list[dict[str, Any]] = []
    for attempt in attempts:
        if not attempt.tables:
            rows.append(
                {
                    "page_number": attempt.page_number,
                    "strategy": attempt.strategy,
                    "crop_table_index": attempt.crop_table_index,
                    "extracted_table_index": "",
                    "row_count": 0,
                    "column_count": 0,
                    "year_columns": "",
                    "metric_label_count": 0,
                    "metric_value_count": 0,
                    "quality_score": 0,
                    "error": attempt.extraction_error or "",
                    "csv_path": "",
                }
            )
            continue
        for table in attempt.tables:
            rows.append(
                {
                    "page_number": attempt.page_number,
                    "strategy": attempt.strategy,
                    "crop_table_index": attempt.crop_table_index,
                    "extracted_table_index": table["extracted_table_index"],
                    "row_count": table["row_count"],
                    "column_count": table["column_count"],
                    "year_columns": json.dumps(
                        table["detected_year_columns"],
                        sort_keys=True,
                    ),
                    "metric_label_count": table["detected_metric_label_count"],
                    "metric_value_count": table["metric_value_count"],
                    "quality_score": table["quality_score"],
                    "error": attempt.extraction_error or "",
                    "csv_path": table["csv_path"],
                }
            )

    with path.open("w", newline="", encoding="utf-8") as csv_file:
        writer = csv.DictWriter(
            csv_file,
            fieldnames=[
                "page_number",
                "strategy",
                "crop_table_index",
                "extracted_table_index",
                "row_count",
                "column_count",
                "year_columns",
                "metric_label_count",
                "metric_value_count",
                "quality_score",
                "error",
                "csv_path",
            ],
        )
        writer.writeheader()
        writer.writerows(rows)


def _load_detections_json(path: Path) -> dict[int, list[DetectionBox]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    detections_by_page: dict[int, list[DetectionBox]] = {}
    for page, detections in payload.items():
        detections_by_page[int(page)] = [
            DetectionBox(**detection) for detection in detections
        ]
    return detections_by_page


def _write_json(path: Path, payload: Any) -> None:
    path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


def _write_rows_csv(path: Path, rows: Sequence[Sequence[str]]) -> None:
    with path.open("w", newline="", encoding="utf-8-sig") as csv_file:
        writer = csv.writer(csv_file)
        writer.writerows(rows)


def _artifact_name(
    *,
    page_number: int,
    strategy: str,
    crop_table_index: int | None,
    extracted_table_index: int,
    suffix: str,
) -> str:
    crop = "full" if crop_table_index is None else f"bbox{crop_table_index}"
    return (
        f"page_{page_number:04d}_{strategy}_{crop}_"
        f"table_{extracted_table_index:02d}{suffix}"
    )


def _metric_helper() -> CamelotTableExtractor:
    return CamelotTableExtractor(
        camelot_reader=lambda *args, **kwargs: [],
        pdfplumber_open=lambda *args, **kwargs: None,
    )


def _column_count(rows: Sequence[Sequence[str]]) -> int:
    return max((len(row) for row in rows), default=0)


def _deduplicate_pages(pages: Iterable[int]) -> list[int]:
    seen: set[int] = set()
    deduplicated: list[int] = []
    for page in pages:
        if page in seen:
            continue
        if page <= 0:
            raise ValueError(f"Page numbers must be positive: {page}")
        seen.add(page)
        deduplicated.append(page)
    return deduplicated


def _tensor_to_list(value: Any) -> list[Any]:
    if hasattr(value, "detach"):
        value = value.detach()
    if hasattr(value, "cpu"):
        value = value.cpu()
    if hasattr(value, "tolist"):
        return value.tolist()
    return list(value)


def _format_coord(value: float) -> str:
    return f"{value:.2f}"


def _error_message(exc: Exception) -> str:
    return str(exc) or exc.__class__.__name__


if __name__ == "__main__":
    raise SystemExit(main())
