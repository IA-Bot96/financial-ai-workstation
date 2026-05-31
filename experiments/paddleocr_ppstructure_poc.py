"""Standalone PaddleOCR PP-Structure proof-of-concept for financial tables.

This script is intentionally outside the production OCR pipeline. It renders
selected PDF pages to images, runs PaddleOCR PP-Structure, converts detected
HTML tables to row/cell arrays, and writes:

* a JSON extraction report
* one CSV file per extracted table
* an ExtractedTable-compatible dictionary per table

Install the experimental dependencies separately from production:

    pip install paddleocr paddlepaddle

Example:

    python experiments/paddleocr_ppstructure_poc.py ^
        --pdf "reports/annual_report.pdf" ^
        --pages 20 25 42 ^
        --source-report-year 2024 ^
        --output-dir output/paddleocr_poc
"""

from __future__ import annotations

import argparse
import csv
import importlib.metadata
import json
import logging
import os
import re
import statistics
import tempfile
import traceback
from dataclasses import dataclass
from html.parser import HTMLParser
from pathlib import Path
from typing import Any, Iterable


DEFAULT_RENDER_DPI = 300
DEFAULT_OUTPUT_DIR = Path("output") / "paddleocr_ppstructure_poc"
MAX_DIAGNOSTIC_LABELS = 30

logger = logging.getLogger("paddleocr_ppstructure_poc")


@dataclass(frozen=True)
class _HtmlCell:
    """A parsed HTML table cell with optional row/column span."""

    text: str
    rowspan: int = 1
    colspan: int = 1


class _TableHTMLParser(HTMLParser):
    """Parse PaddleOCR table HTML into rows while preserving spans."""

    def __init__(self) -> None:
        super().__init__()
        self.rows: list[list[_HtmlCell]] = []
        self._current_row: list[_HtmlCell] | None = None
        self._cell_text_parts: list[str] | None = None
        self._rowspan = 1
        self._colspan = 1

    def handle_starttag(
        self,
        tag: str,
        attrs: list[tuple[str, str | None]],
    ) -> None:
        normalized_tag = tag.lower()
        if normalized_tag == "tr":
            self._current_row = []
            return

        if normalized_tag not in {"td", "th"} or self._current_row is None:
            return

        attr_map = {key.lower(): value for key, value in attrs if value is not None}
        self._rowspan = _positive_int(attr_map.get("rowspan"), default=1)
        self._colspan = _positive_int(attr_map.get("colspan"), default=1)
        self._cell_text_parts = []

    def handle_data(self, data: str) -> None:
        if self._cell_text_parts is not None:
            self._cell_text_parts.append(data)

    def handle_endtag(self, tag: str) -> None:
        normalized_tag = tag.lower()
        if normalized_tag in {"td", "th"} and self._cell_text_parts is not None:
            text = _normalize_cell_text("".join(self._cell_text_parts))
            if self._current_row is not None:
                self._current_row.append(
                    _HtmlCell(
                        text=text,
                        rowspan=self._rowspan,
                        colspan=self._colspan,
                    )
                )
            self._cell_text_parts = None
            self._rowspan = 1
            self._colspan = 1
            return

        if normalized_tag == "tr" and self._current_row is not None:
            if self._current_row:
                self.rows.append(self._current_row)
            self._current_row = None


def main() -> int:
    """Run the PaddleOCR PP-Structure table extraction proof-of-concept."""

    args = _parse_args()
    _configure_logging(args.log_level)
    _configure_paddle_runtime(enable_mkldnn=args.enable_mkldnn)

    pdf_path = args.pdf.resolve()
    output_dir = args.output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    csv_dir = output_dir / "csv"
    csv_dir.mkdir(parents=True, exist_ok=True)
    image_dir = output_dir / "rendered_pages"
    if args.keep_images:
        image_dir.mkdir(parents=True, exist_ok=True)

    page_numbers = _parse_page_numbers(args.pages)
    source_report_year = args.source_report_year or _infer_year_from_filename(
        pdf_path,
    )

    logger.info(
        "Starting PaddleOCR PP-Structure POC",
        extra={
            "pdf_path": str(pdf_path),
            "pages": page_numbers,
            "output_dir": str(output_dir),
            "source_report_year": source_report_year,
            "dpi": args.dpi,
            "device": args.device,
            "engine": args.engine,
            "enable_mkldnn": args.enable_mkldnn,
        },
    )
    engine = _load_ppstructure_engine(
        show_log=args.show_paddle_logs,
        device=args.device,
        engine=args.engine,
        enable_mkldnn=args.enable_mkldnn,
        cpu_threads=args.cpu_threads,
    )
    logger.info("PaddleOCR PP-Structure initialized")

    with tempfile.TemporaryDirectory(prefix="paddleocr_ppstructure_") as temp_dir:
        report = _run_extraction(
            pdf_path=pdf_path,
            page_numbers=page_numbers,
            output_dir=output_dir,
            csv_dir=csv_dir,
            image_dir=image_dir if args.keep_images else Path(temp_dir),
            keep_images=args.keep_images,
            source_report_year=source_report_year,
            render_dpi=args.dpi,
            engine=engine,
            include_tracebacks=args.tracebacks,
        )

    output_json_path = args.output_json or output_dir / "paddleocr_extraction_report.json"
    output_json_path = output_json_path.resolve()
    output_json_path.parent.mkdir(parents=True, exist_ok=True)
    output_json_path.write_text(
        json.dumps(report, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    print(json.dumps(report["summary"], indent=2, ensure_ascii=False))
    print(f"JSON report: {output_json_path}")
    print(f"CSV directory: {csv_dir}")
    return 0 if report["summary"]["tables_extracted"] > 0 else 2


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Run standalone PaddleOCR PP-Structure table extraction on selected "
            "annual-report PDF pages."
        )
    )
    parser.add_argument(
        "--pdf",
        required=True,
        type=Path,
        help="Path to the annual-report PDF.",
    )
    parser.add_argument(
        "--pages",
        nargs="+",
        required=True,
        help=(
            "One-based page numbers, comma lists, or ranges. Examples: "
            "20 25 42, 20,25,42, 20-22."
        ),
    )
    parser.add_argument(
        "--source-report-year",
        type=int,
        default=None,
        help=(
            "Optional annual report year. If omitted, the script attempts to "
            "infer it from the PDF file name."
        ),
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_OUTPUT_DIR,
        help=f"Directory for JSON/CSV outputs. Default: {DEFAULT_OUTPUT_DIR}",
    )
    parser.add_argument(
        "--output-json",
        type=Path,
        default=None,
        help="Optional explicit JSON output path.",
    )
    parser.add_argument(
        "--dpi",
        type=int,
        default=DEFAULT_RENDER_DPI,
        help=f"PDF render DPI. Default: {DEFAULT_RENDER_DPI}",
    )
    parser.add_argument(
        "--keep-images",
        action="store_true",
        help="Persist rendered page images under the output directory.",
    )
    parser.add_argument(
        "--show-paddle-logs",
        action="store_true",
        help="Show PaddleOCR logs while running the experiment.",
    )
    parser.add_argument(
        "--log-level",
        default="INFO",
        choices=("DEBUG", "INFO", "WARNING", "ERROR"),
        help="POC logging level. Default: INFO.",
    )
    parser.add_argument(
        "--tracebacks",
        action="store_true",
        help="Include full Python tracebacks in the JSON report for failed pages.",
    )
    parser.add_argument(
        "--device",
        default="cpu",
        help="PaddleOCR device. Default: cpu.",
    )
    parser.add_argument(
        "--engine",
        default="paddle_static",
        choices=("paddle", "paddle_static", "paddle_dynamic", "transformers"),
        help="PaddleOCR inference engine. Default: paddle_static.",
    )
    parser.add_argument(
        "--enable-mkldnn",
        action="store_true",
        help=(
            "Enable MKLDNN/oneDNN acceleration. Disabled by default because "
            "PaddleOCR 3.6 CPU inference can fail on some Windows machines."
        ),
    )
    parser.add_argument(
        "--cpu-threads",
        type=int,
        default=4,
        help="CPU threads for Paddle inference. Default: 4.",
    )
    return parser.parse_args()


def _configure_logging(level: str) -> None:
    """Configure console logging for the standalone proof-of-concept."""

    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s - %(message)s",
    )


def _configure_paddle_runtime(*, enable_mkldnn: bool) -> None:
    """Set conservative Paddle CPU flags before importing PaddleOCR."""

    if enable_mkldnn:
        return

    os.environ.setdefault("FLAGS_use_mkldnn", "0")
    os.environ.setdefault("FLAGS_use_onednn", "0")


def _run_extraction(
    *,
    pdf_path: Path,
    page_numbers: list[int],
    output_dir: Path,
    csv_dir: Path,
    image_dir: Path,
    keep_images: bool,
    source_report_year: int | None,
    render_dpi: int,
    engine: Any,
    include_tracebacks: bool,
) -> dict[str, Any]:
    """Render requested pages, run PP-Structure, and build the JSON report."""

    try:
        import fitz
    except ImportError as exc:
        raise RuntimeError(
            "PyMuPDF is required for rendering PDF pages. Install pymupdf."
        ) from exc

    pages: list[dict[str, Any]] = []
    all_table_scores: list[float] = []
    document = fitz.open(pdf_path)
    try:
        total_pdf_pages = len(document)
        logger.info(
            "PDF opened for rendering",
            extra={"pdf_path": str(pdf_path), "total_pdf_pages": total_pdf_pages},
        )
        for page_number in page_numbers:
            page_report: dict[str, Any] = {
                "page_number": page_number,
                "status": "pending",
                "stage": "queued",
                "error": None,
                "error_traceback": None,
                "rendered_image_path": None,
                "tables": [],
                "diagnostics": {
                    "tables_extracted": 0,
                    "best_quality_score": 0.0,
                    "assessment": "not_processed",
                },
            }

            logger.info(
                "Processing page",
                extra={"page_number": page_number, "total_pdf_pages": total_pdf_pages},
            )
            if page_number < 1 or page_number > total_pdf_pages:
                page_report["status"] = "skipped"
                page_report["stage"] = "page_range_validation"
                page_report["error"] = (
                    f"Page {page_number} is outside PDF range 1-{total_pdf_pages}."
                )
                logger.warning(
                    "Page skipped because it is outside the PDF range",
                    extra={
                        "page_number": page_number,
                        "total_pdf_pages": total_pdf_pages,
                    },
                )
                pages.append(page_report)
                continue

            image_path = image_dir / f"page_{page_number:04d}_{render_dpi}dpi.png"
            try:
                page_report["stage"] = "rendering"
                _render_pdf_page(
                    document=document,
                    page_number=page_number,
                    image_path=image_path,
                    dpi=render_dpi,
                )
            except Exception as exc:
                page_report["status"] = "failed"
                page_report["stage"] = "rendering"
                page_report["error"] = str(exc) or exc.__class__.__name__
                if include_tracebacks:
                    page_report["error_traceback"] = traceback.format_exc()
                logger.exception(
                    "Page rendering failed",
                    extra={"page_number": page_number, "image_path": str(image_path)},
                )
                pages.append(page_report)
                continue

            if keep_images:
                page_report["rendered_image_path"] = str(image_path)
            logger.info(
                "Page rendered",
                extra={
                    "page_number": page_number,
                    "image_path": str(image_path),
                    "image_bytes": image_path.stat().st_size
                    if image_path.exists()
                    else None,
                },
            )

            try:
                page_report["stage"] = "ocr_execution"
                logger.info(
                    "Running PP-Structure OCR",
                    extra={"page_number": page_number, "image_path": str(image_path)},
                )
                structure_items = _run_ppstructure(engine, image_path)
            except Exception as exc:
                page_report["status"] = "failed"
                page_report["stage"] = "ocr_execution"
                page_report["error"] = str(exc) or exc.__class__.__name__
                if include_tracebacks:
                    page_report["error_traceback"] = traceback.format_exc()
                logger.exception(
                    "PP-Structure OCR failed",
                    extra={"page_number": page_number, "image_path": str(image_path)},
                )
                pages.append(page_report)
                continue

            table_items = _table_items(structure_items)
            logger.info(
                "PP-Structure OCR completed",
                extra={
                    "page_number": page_number,
                    "structure_item_count": len(structure_items),
                    "table_item_count": len(table_items),
                },
            )
            page_tables: list[dict[str, Any]] = []
            for table_index, item in enumerate(table_items):
                rows = _rows_from_structure_item(item)
                if not rows:
                    continue

                effective_source_year = source_report_year or _infer_year_from_rows(rows)
                diagnostics = _table_diagnostics(rows)
                all_table_scores.append(diagnostics["quality_score"])
                csv_path = csv_dir / (
                    f"page_{page_number:04d}_table_{table_index:02d}.csv"
                )
                _write_csv(csv_path, rows)

                extracted_table = {
                    "source_report_year": effective_source_year,
                    "page_number": page_number,
                    "table_type": "unclassified_table",
                    "table_index": table_index,
                    "rows": rows,
                    "metric_values": [],
                }
                page_tables.append(
                    {
                        "table_index": table_index,
                        "engine": "paddleocr_ppstructure",
                        "bbox": _serializable_bbox(item.get("bbox")),
                        "confidence": _serializable_confidence(item),
                        "csv_path": str(csv_path),
                        "diagnostics": diagnostics,
                        "extracted_table": extracted_table,
                    }
                )

            page_report["tables"] = page_tables
            page_report["status"] = "processed"
            page_report["stage"] = "complete"
            page_report["diagnostics"] = _page_diagnostics(page_tables)
            logger.info(
                "Page processed",
                extra={
                    "page_number": page_number,
                    "tables_extracted": len(page_tables),
                    "assessment": page_report["diagnostics"]["assessment"],
                },
            )
            pages.append(page_report)
    finally:
        document.close()

    return {
        "pdf_path": str(pdf_path),
        "output_dir": str(output_dir),
        "page_numbers": page_numbers,
        "render_dpi": render_dpi,
        "source_report_year": source_report_year,
        "pages": pages,
        "summary": _summary(
            pages=pages,
            requested_pages=page_numbers,
            table_scores=all_table_scores,
        ),
    }


def _load_ppstructure_engine(
    *,
    show_log: bool,
    device: str,
    engine: str,
    enable_mkldnn: bool,
    cpu_threads: int,
) -> Any:
    """Load PaddleOCR PP-Structure without importing it at module import time."""

    try:
        from paddleocr import PPStructure

        engine_class = PPStructure
    except ImportError:
        try:
            from paddleocr import PPStructureV3

            engine_class = PPStructureV3
        except ImportError as exc:
            raise RuntimeError(
                "PaddleOCR PP-Structure is not installed. Install the "
                "experimental dependencies with: pip install paddleocr paddlepaddle"
            ) from exc

    init_attempts = (
        {
            "device": device,
            "engine": engine,
            "enable_mkldnn": enable_mkldnn,
            "enable_hpi": False,
            "enable_cinn": False,
            "cpu_threads": cpu_threads,
            "use_doc_orientation_classify": False,
            "use_doc_unwarping": False,
            "use_textline_orientation": False,
            "use_table_recognition": True,
            "use_region_detection": False,
            "use_formula_recognition": False,
            "use_seal_recognition": False,
            "use_chart_recognition": False,
        },
        {
            "device": device,
            "engine": engine,
            "enable_mkldnn": enable_mkldnn,
            "enable_hpi": False,
            "enable_cinn": False,
            "cpu_threads": cpu_threads,
        },
        {
            "show_log": show_log,
            "image_orientation": True,
            "recovery": False,
        },
        {"show_log": show_log, "image_orientation": True},
        {"show_log": show_log},
        {},
    )
    last_error: Exception | None = None
    for kwargs in init_attempts:
        try:
            logger.debug(
                "Attempting PP-Structure initialization",
                extra={"init_kwargs": kwargs},
            )
            return engine_class(**kwargs)
        except (TypeError, ValueError) as exc:
            last_error = exc
            logger.debug(
                "PP-Structure initialization attempt rejected",
                extra={"init_kwargs": kwargs, "error": str(exc)},
            )
            continue
        except RuntimeError as exc:
            if _is_missing_paddlex_ocr_extra_error(exc):
                raise RuntimeError(_paddlex_ocr_extra_install_message()) from exc
            last_error = exc
            logger.debug(
                "PP-Structure initialization attempt failed",
                extra={"init_kwargs": kwargs, "error": str(exc)},
            )
            continue

    raise RuntimeError("Could not initialize PaddleOCR PP-Structure.") from last_error


def _is_missing_paddlex_ocr_extra_error(exc: RuntimeError) -> bool:
    """Return True when PaddleX OCR optional dependencies are missing."""

    message = str(exc).lower()
    return (
        "dependency error" in message
        and "pipeline creation" in message
        and "required dependencies" in message
    )


def _paddlex_ocr_extra_install_message() -> str:
    """Return an actionable install command for PaddleX OCR extras."""

    try:
        paddlex_version = importlib.metadata.version("paddlex")
    except importlib.metadata.PackageNotFoundError:
        paddlex_version = None

    version_suffix = f"=={paddlex_version}" if paddlex_version else ""
    return (
        "PP-StructureV3 requires PaddleX OCR optional dependencies. Install "
        "them with:\n\n"
        f'python -m pip install "paddlex[ocr]{version_suffix}"\n'
    )


def _run_ppstructure(engine: Any, image_path: Path) -> list[dict[str, Any]]:
    """Run PP-Structure and normalize the top-level result to dictionaries."""

    if callable(engine):
        result = engine(str(image_path))
    elif hasattr(engine, "predict"):
        result = engine.predict(str(image_path))
    else:
        raise RuntimeError("PaddleOCR engine is neither callable nor predictable.")

    return _normalize_structure_result(result)


def _normalize_structure_result(result: Any) -> list[dict[str, Any]]:
    """Convert common PaddleOCR result shapes into plain dictionaries."""

    if result is None:
        return []

    if isinstance(result, dict):
        if "res" in result or "type" in result:
            return [result]
        for key in ("result", "results", "data", "items"):
            value = result.get(key)
            if isinstance(value, list):
                return _normalize_structure_result(value)
        return [result]

    if isinstance(result, list):
        normalized: list[dict[str, Any]] = []
        for item in result:
            normalized.extend(_normalize_structure_result(item))
        return normalized

    if hasattr(result, "to_dict"):
        return _normalize_structure_result(result.to_dict())

    if hasattr(result, "to_json"):
        json_value = result.to_json()
        if isinstance(json_value, str):
            return _normalize_structure_result(json.loads(json_value))
        return _normalize_structure_result(json_value)

    if hasattr(result, "json"):
        json_value = result.json
        if callable(json_value):
            json_value = json_value()
        if isinstance(json_value, str):
            return _normalize_structure_result(json.loads(json_value))
        return _normalize_structure_result(json_value)

    if hasattr(result, "__iter__") and not isinstance(result, (str, bytes)):
        return _normalize_structure_result(list(result))

    return []


def _render_pdf_page(
    *,
    document: Any,
    page_number: int,
    image_path: Path,
    dpi: int,
) -> None:
    """Render one PDF page to a PNG image for OCR."""

    image_path.parent.mkdir(parents=True, exist_ok=True)
    page = document.load_page(page_number - 1)
    zoom = dpi / 72
    try:
        import fitz

        matrix = fitz.Matrix(zoom, zoom)
    except ImportError as exc:
        raise RuntimeError("PyMuPDF is required for rendering PDF pages.") from exc

    pixmap = page.get_pixmap(matrix=matrix, alpha=False)
    pixmap.save(image_path)


def _table_items(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Return only PP-Structure items that appear to contain table output."""

    table_items: list[dict[str, Any]] = []
    for item in items:
        item_type = str(item.get("type", "")).lower()
        if "table" in item_type or _extract_html(item):
            table_items.append(item)
    return table_items


def _rows_from_structure_item(item: dict[str, Any]) -> list[list[str]]:
    """Extract row arrays from a PP-Structure table item."""

    html = _extract_html(item)
    if not html:
        return []
    return _rows_from_html(html)


def _extract_html(item: dict[str, Any]) -> str | None:
    """Find an HTML table string in common PP-Structure result shapes."""

    direct_html = item.get("html")
    if isinstance(direct_html, str) and "<table" in direct_html.lower():
        return direct_html

    result = item.get("res")
    if isinstance(result, str) and "<table" in result.lower():
        return result
    if isinstance(result, dict):
        html = result.get("html") or result.get("table_html")
        if isinstance(html, str) and "<table" in html.lower():
            return html

    return None


def _rows_from_html(html: str) -> list[list[str]]:
    parser = _TableHTMLParser()
    parser.feed(html)
    return _normalize_rows(_expand_spans(parser.rows))


def _expand_spans(rows: list[list[_HtmlCell]]) -> list[list[str]]:
    """Expand HTML rowspan/colspan into a rectangular-ish string grid."""

    expanded_rows: list[list[str]] = []
    active_spans: dict[int, tuple[int, str]] = {}

    for row in rows:
        output_row: list[str] = []
        next_active_spans: dict[int, tuple[int, str]] = {}
        consumed_active_columns: set[int] = set()
        column_index = 0

        def fill_active_until_free_column() -> None:
            nonlocal column_index
            while column_index in active_spans:
                remaining_rows, text = active_spans[column_index]
                output_row.append(text)
                consumed_active_columns.add(column_index)
                if remaining_rows > 1:
                    next_active_spans[column_index] = (remaining_rows - 1, text)
                column_index += 1

        for cell in row:
            fill_active_until_free_column()
            for span_column in range(column_index, column_index + cell.colspan):
                output_row.append(cell.text)
                if cell.rowspan > 1:
                    next_active_spans[span_column] = (cell.rowspan - 1, cell.text)
            column_index += cell.colspan

        for span_column in sorted(active_spans):
            if span_column in consumed_active_columns:
                continue
            while len(output_row) < span_column:
                output_row.append("")
            remaining_rows, text = active_spans[span_column]
            output_row.append(text)
            if remaining_rows > 1:
                next_active_spans[span_column] = (remaining_rows - 1, text)

        expanded_rows.append(output_row)
        active_spans = next_active_spans

    max_columns = max((len(row) for row in expanded_rows), default=0)
    return [row + [""] * (max_columns - len(row)) for row in expanded_rows]


def _normalize_rows(rows: Iterable[Iterable[Any]]) -> list[list[str]]:
    normalized_rows: list[list[str]] = []
    for row in rows:
        normalized_row = [_normalize_cell_text(str(cell)) for cell in row]
        if any(cell for cell in normalized_row):
            normalized_rows.append(normalized_row)
    return normalized_rows


def _table_diagnostics(rows: list[list[str]]) -> dict[str, Any]:
    """Return diagnostics required to judge financial table extraction quality."""

    row_count = len(rows)
    column_count = max((len(row) for row in rows), default=0)
    detected_year_columns = _detected_year_columns(rows)
    detected_metric_labels = _detected_metric_labels(rows)
    total_cells = row_count * column_count
    non_empty_cells = sum(1 for row in rows for cell in row if cell.strip())
    numeric_cells = sum(1 for row in rows for cell in row if _looks_numeric(cell))
    non_empty_ratio = non_empty_cells / total_cells if total_cells else 0.0
    quality_score = _quality_score(
        row_count=row_count,
        column_count=column_count,
        detected_year_columns=detected_year_columns,
        detected_metric_labels=detected_metric_labels,
        non_empty_ratio=non_empty_ratio,
        numeric_cells=numeric_cells,
    )

    return {
        "row_count": row_count,
        "column_count": column_count,
        "detected_year_columns": detected_year_columns,
        "detected_metric_labels": detected_metric_labels,
        "detected_metric_label_count": len(detected_metric_labels),
        "non_empty_cell_count": non_empty_cells,
        "numeric_cell_count": numeric_cells,
        "non_empty_cell_ratio": round(non_empty_ratio, 4),
        "quality_score": quality_score,
        "assessment": _assessment_label(quality_score),
        "assessment_reasons": _assessment_reasons(
            row_count=row_count,
            column_count=column_count,
            detected_year_columns=detected_year_columns,
            detected_metric_labels=detected_metric_labels,
            non_empty_ratio=non_empty_ratio,
        ),
    }


def _detected_year_columns(rows: list[list[str]]) -> list[dict[str, Any]]:
    years_by_column: dict[int, set[int]] = {}
    for row in rows:
        for column_index, cell in enumerate(row):
            for year in _years_in_text(cell):
                years_by_column.setdefault(column_index, set()).add(year)

    return [
        {
            "column_index": column_index,
            "years": sorted(years),
        }
        for column_index, years in sorted(years_by_column.items())
    ]


def _detected_metric_labels(rows: list[list[str]]) -> list[str]:
    labels: list[str] = []
    seen: set[str] = set()
    for row in rows:
        label = _first_metric_like_cell(row)
        if label is None:
            continue

        normalized = label.lower()
        if normalized in seen:
            continue
        labels.append(label)
        seen.add(normalized)
        if len(labels) >= MAX_DIAGNOSTIC_LABELS:
            break
    return labels


def _first_metric_like_cell(row: list[str]) -> str | None:
    for cell in row:
        text = cell.strip()
        if not text:
            continue
        if re.fullmatch(r"(?:19|20)\d{2}", text):
            continue
        if not re.search(r"[A-Za-z]", text):
            continue
        if len(text) > 100:
            continue
        return text
    return None


def _quality_score(
    *,
    row_count: int,
    column_count: int,
    detected_year_columns: list[dict[str, Any]],
    detected_metric_labels: list[str],
    non_empty_ratio: float,
    numeric_cells: int,
) -> float:
    score = 0.0
    if row_count >= 3:
        score += 20
    elif row_count > 0:
        score += 8

    if column_count >= 2:
        score += 20
    elif column_count == 1:
        score += 5

    if detected_year_columns:
        score += 25

    if len(detected_metric_labels) >= 3:
        score += 20
    elif detected_metric_labels:
        score += 10

    if numeric_cells >= 3:
        score += 10
    elif numeric_cells:
        score += 5

    if non_empty_ratio >= 0.6:
        score += 5
    elif non_empty_ratio >= 0.35:
        score += 2

    return round(min(score, 100.0), 2)


def _assessment_label(score: float) -> str:
    if score >= 85:
        return "excellent"
    if score >= 70:
        return "good"
    if score >= 50:
        return "fair"
    return "poor"


def _assessment_reasons(
    *,
    row_count: int,
    column_count: int,
    detected_year_columns: list[dict[str, Any]],
    detected_metric_labels: list[str],
    non_empty_ratio: float,
) -> list[str]:
    reasons: list[str] = []
    if row_count < 3:
        reasons.append("Few extracted rows; table structure may be incomplete.")
    if column_count < 2:
        reasons.append("Fewer than two columns detected.")
    if not detected_year_columns:
        reasons.append("No year columns detected.")
    if len(detected_metric_labels) < 3:
        reasons.append("Few metric-like row labels detected.")
    if non_empty_ratio < 0.35:
        reasons.append("Low non-empty cell ratio.")
    if not reasons:
        reasons.append("Table has rows, columns, year references, and metric labels.")
    return reasons


def _page_diagnostics(page_tables: list[dict[str, Any]]) -> dict[str, Any]:
    if not page_tables:
        return {
            "tables_extracted": 0,
            "best_quality_score": 0.0,
            "assessment": "poor",
        }

    scores = [
        table["diagnostics"]["quality_score"]
        for table in page_tables
    ]
    return {
        "tables_extracted": len(page_tables),
        "best_quality_score": max(scores),
        "assessment": _assessment_label(max(scores)),
    }


def _summary(
    *,
    pages: list[dict[str, Any]],
    requested_pages: list[int],
    table_scores: list[float],
) -> dict[str, Any]:
    processed_pages = [page for page in pages if page["status"] == "processed"]
    all_tables = [
        table
        for page in pages
        for table in page.get("tables", [])
    ]
    tables_with_year_columns = [
        table
        for table in all_tables
        if table["diagnostics"]["detected_year_columns"]
    ]
    tables_with_metric_labels = [
        table
        for table in all_tables
        if table["diagnostics"]["detected_metric_labels"]
    ]
    average_quality_score = (
        round(statistics.mean(table_scores), 2) if table_scores else 0.0
    )
    return {
        "pages_requested": len(requested_pages),
        "pages_processed": len(processed_pages),
        "tables_extracted": len(all_tables),
        "tables_with_year_columns": len(tables_with_year_columns),
        "tables_with_metric_labels": len(tables_with_metric_labels),
        "average_quality_score": average_quality_score,
        "assessment": _assessment_label(average_quality_score),
    }


def _write_csv(path: Path, rows: list[list[str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8-sig") as csv_file:
        writer = csv.writer(csv_file)
        writer.writerows(rows)


def _parse_page_numbers(values: list[str]) -> list[int]:
    page_numbers: list[int] = []
    for value in values:
        for token in value.split(","):
            stripped = token.strip()
            if not stripped:
                continue
            if "-" in stripped:
                start_text, end_text = stripped.split("-", 1)
                start = int(start_text)
                end = int(end_text)
                if start > end:
                    raise ValueError(f"Invalid descending page range: {stripped}")
                page_numbers.extend(range(start, end + 1))
                continue
            page_numbers.append(int(stripped))

    deduplicated: list[int] = []
    seen: set[int] = set()
    for page_number in page_numbers:
        if page_number < 1:
            raise ValueError("Page numbers must be greater than zero.")
        if page_number in seen:
            continue
        deduplicated.append(page_number)
        seen.add(page_number)
    return deduplicated


def _years_in_text(text: str) -> list[int]:
    return [
        int(match.group(0))
        for match in re.finditer(r"\b(?:19|20)\d{2}\b", text)
    ]


def _infer_year_from_filename(pdf_path: Path) -> int | None:
    years = _years_in_text(pdf_path.stem)
    return max(years) if years else None


def _infer_year_from_rows(rows: list[list[str]]) -> int | None:
    years = [
        year
        for row in rows
        for cell in row
        for year in _years_in_text(cell)
    ]
    return max(years) if years else None


def _looks_numeric(value: str) -> bool:
    text = value.strip().replace(",", "")
    text = text.replace("\u2212", "-")
    text = re.sub(r"(?i)\b(rs|pkr|usd|eur|gbp|rupees|million|mn|thousand)\b", "", text)
    return re.search(r"^\(?[-+]?\d+(?:\.\d+)?\)?$", text.strip()) is not None


def _serializable_bbox(value: Any) -> list[float] | None:
    if value is None:
        return None
    if isinstance(value, (list, tuple)):
        serializable: list[float] = []
        for item in value:
            try:
                serializable.append(float(item))
            except (TypeError, ValueError):
                return None
        return serializable
    return None


def _serializable_confidence(item: dict[str, Any]) -> float | None:
    for key in ("confidence", "score"):
        value = item.get(key)
        if value is None:
            continue
        try:
            return float(value)
        except (TypeError, ValueError):
            continue
    return None


def _normalize_cell_text(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def _positive_int(value: str | None, *, default: int) -> int:
    if value is None:
        return default
    try:
        parsed = int(value)
    except ValueError:
        return default
    return max(parsed, 1)


if __name__ == "__main__":
    raise SystemExit(main())
