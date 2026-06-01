"""Audit whether true multi-logical tables can be split after extraction.

This is a standalone experiment. It does not modify production OCR code.
"""

from __future__ import annotations

import argparse
import contextlib
import json
import logging
import os
import re
import shutil
import sys
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = PROJECT_ROOT / "backend"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from ocr_engine.models.financial_table_classification import (  # noqa: E402
    FinancialTableClassificationResult,
)
from ocr_engine.models.table_detection_result import TableDetectionResult  # noqa: E402
from ocr_engine.services.camelot_table_extractor import (  # noqa: E402
    UNCLASSIFIED_TABLE_TYPE,
    CamelotTableExtractor,
    _contains_phrase,
    _normalize_key,
    _normalize_text,
    _table_type_match_score,
)

FOCUS_PAGES = (163, 164, 321)
CONTEXT_PATH = PROJECT_ROOT / "output" / "lucky-cement_insights_diagnostics_context.json"
OUTPUT_PATH = PROJECT_ROOT / "output" / "table_splitting_feasibility_audit.json"
LOG_PATH = PROJECT_ROOT / "output" / "table_splitting_feasibility_audit.log"


@dataclass(frozen=True)
class LogicalSplit:
    """A simulated logical section split from one physical extracted table."""

    table_index: int
    section_index: int
    start_row: int
    end_row: int
    table_type: str
    split_reason: str
    boundary_signal: str
    rows: list[list[str]]


def main() -> int:
    """Generate the table-splitting feasibility audit JSON."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--context-json", default=str(CONTEXT_PATH))
    parser.add_argument("--output", default=str(OUTPUT_PATH))
    parser.add_argument("--log-file", default=str(LOG_PATH))
    args = parser.parse_args()

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    log_path = Path(args.log_file)
    log_path.parent.mkdir(parents=True, exist_ok=True)
    _configure_workspace_temp(output_path.parent)
    logging.disable(logging.CRITICAL)

    context = json.loads(Path(args.context_json).read_text(encoding="utf-8"))
    report = context["reports"][0]
    source_report_year = int(report["year"])
    pdf_path = report["file_path"]
    classification_result = FinancialTableClassificationResult.model_validate(
        context["classification_results"][str(source_report_year)]
    )
    detection_result = TableDetectionResult.model_validate(
        context["table_detection_results"][str(source_report_year)]
    )
    page_table_types = {
        page.page_number: page
        for page in classification_result.page_table_types
        if page.page_number in FOCUS_PAGES
    }
    detected_counts = {
        page.page_number: page.tables_detected
        for page in detection_result.detected_pages
        if page.page_number in FOCUS_PAGES
    }

    extractor = CamelotTableExtractor()
    pages: list[dict[str, Any]] = []
    with log_path.open("w", encoding="utf-8") as log_handle:
        with contextlib.redirect_stderr(log_handle):
            for page_number in FOCUS_PAGES:
                page_table_type = page_table_types[page_number]
                raw_extraction = extractor._extract_page_tables(pdf_path, page_number)
                current_tables, current_diagnostic = extractor._build_extracted_tables(
                    page_table_type=page_table_type,
                    raw_tables=raw_extraction.raw_tables,
                    detected_table_count=detected_counts.get(page_number, 0),
                    extraction_strategy=raw_extraction.strategy,
                    extraction_quality=raw_extraction.quality,
                )
                split_tables = [
                    split
                    for table_index, rows in enumerate(raw_extraction.raw_tables)
                    for split in _simulate_splits(page_number, table_index, rows)
                ]
                pages.append(
                    _page_report(
                        extractor=extractor,
                        page_number=page_number,
                        page_table_types=page_table_type.table_types,
                        raw_table_count=len(raw_extraction.raw_tables),
                        extraction_strategy=raw_extraction.strategy,
                        current_tables=current_tables,
                        current_diagnostic=current_diagnostic,
                        split_tables=split_tables,
                        source_report_year=source_report_year,
                    )
                )

    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "audit": "table_splitting_feasibility",
        "production_code_modified": False,
        "company_name": context.get("company_name"),
        "source_report_year": source_report_year,
        "pdf_path": pdf_path,
        "focus_pages": list(FOCUS_PAGES),
        "summary": _summary(pages),
        "recommendation": _recommendation(pages),
        "pages": pages,
        "log_file": str(log_path),
    }
    output_path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    print(f"Wrote {output_path}")
    return 0


def _page_report(
    *,
    extractor: CamelotTableExtractor,
    page_number: int,
    page_table_types: list[str],
    raw_table_count: int,
    extraction_strategy: str,
    current_tables: list[Any],
    current_diagnostic: Any,
    split_tables: list[LogicalSplit],
    source_report_year: int,
) -> dict[str, Any]:
    classified_type_keys = {_normalize_key(table_type) for table_type in page_table_types}
    simulated_types = [split.table_type for split in split_tables]
    simulated_type_keys = {_normalize_key(table_type) for table_type in simulated_types}
    current_unmatched = len(current_diagnostic.unmatched_classifications)
    simulated_unmatched = len(classified_type_keys - simulated_type_keys)
    current_unclassified = sum(
        1
        for table in current_tables
        if _normalize_key(table.table_type) == UNCLASSIFIED_TABLE_TYPE
    )
    simulated_unclassified = sum(
        1
        for split in split_tables
        if _normalize_key(split.table_type) == UNCLASSIFIED_TABLE_TYPE
    )
    split_metrics = [
        metric_value
        for split in split_tables
        for metric_value in extractor._extract_metric_values(
            rows=split.rows,
            source_report_year=source_report_year,
            page_number=page_number,
            table_type=split.table_type,
        )
    ]
    current_metrics = [
        metric_value for table in current_tables for metric_value in table.metric_values
    ]
    return {
        "page_number": page_number,
        "current_extracted_table_count": raw_table_count,
        "simulated_split_table_count": len(split_tables),
        "classified_table_types": page_table_types,
        "resulting_logical_table_types": simulated_types,
        "extraction_strategy": extraction_strategy,
        "current_matching": {
            "matched_table_count": current_diagnostic.matched_table_count,
            "unmatched_classified_types": current_diagnostic.unmatched_classifications,
            "unclassified_tables": current_unclassified,
            "assigned_table_types": [table.table_type for table in current_tables],
            "metric_values": len(current_metrics),
        },
        "simulated_matching": {
            "matched_classified_type_count": len(classified_type_keys & simulated_type_keys),
            "unmatched_classified_types": sorted(classified_type_keys - simulated_type_keys),
            "unclassified_tables": simulated_unclassified,
            "metric_values": len(split_metrics),
        },
        "estimated_impact": {
            "additional_matched_tables": (
                len(classified_type_keys & simulated_type_keys)
                - current_diagnostic.matched_table_count
            ),
            "reduction_in_unmatched_classified_types": (
                current_unmatched - simulated_unmatched
            ),
            "reduction_in_unclassified_tables": (
                current_unclassified - simulated_unclassified
            ),
            "metric_values_affected": len(current_metrics),
            "simulated_metric_values": len(split_metrics),
        },
        "separability_signals": _separability_signals(
            page_number=page_number,
            rows=current_tables[0].rows if current_tables else [],
        ),
        "split_sections": [
            _split_payload(
                extractor=extractor,
                split=split,
                source_report_year=source_report_year,
                page_number=page_number,
                classified_table_types=page_table_types,
            )
            for split in split_tables
        ],
        "feasibility": _page_feasibility(page_number, split_tables),
    }


def _simulate_splits(
    page_number: int,
    table_index: int,
    rows: list[list[str]],
) -> list[LogicalSplit]:
    if page_number in {163, 164}:
        return _split_analysis_table(page_number, table_index, rows)
    if page_number == 321:
        return _split_note_table(page_number, table_index, rows)
    return [
        LogicalSplit(
            table_index=table_index,
            section_index=0,
            start_row=0,
            end_row=max(0, len(rows) - 1),
            table_type=UNCLASSIFIED_TABLE_TYPE,
            split_reason="no_page_specific_split_rule",
            boundary_signal="none",
            rows=rows,
        )
    ]


def _split_analysis_table(
    page_number: int,
    table_index: int,
    rows: list[list[str]],
) -> list[LogicalSplit]:
    markers: list[tuple[int, str, str, str]] = [(0, _primary_type_for_page(page_number), "table_start", "start")]
    for index, row in enumerate(rows):
        text = _row_text(row)
        normalized = _normalize_text(text)
        compact = _compact(normalized)
        if "verticalanalysis" in compact:
            markers.append((index, "vertical_analysis", "heading_row", text))
        if "horizontalanalysis" in compact:
            # Keep the first horizontal-analysis heading as a section boundary.
            if not any(marker[1] == "horizontal_analysis" for marker in markers):
                markers.append((index, "horizontal_analysis", "heading_row", text))
    return _build_sections_from_markers(table_index, rows, markers)


def _split_note_table(
    page_number: int,
    table_index: int,
    rows: list[list[str]],
) -> list[LogicalSplit]:
    header_rows = rows[:2]
    markers: list[tuple[int, str, str, str]] = []
    for index, row in enumerate(rows):
        text = _row_text(row)
        if _note_reference(text):
            markers.append(
                (
                    index,
                    "notes",
                    "note_reference_row",
                    text,
                )
            )
    if not markers:
        return [
            LogicalSplit(
                table_index=table_index,
                section_index=0,
                start_row=0,
                end_row=max(0, len(rows) - 1),
                table_type=UNCLASSIFIED_TABLE_TYPE,
                split_reason="no_note_references_found",
                boundary_signal="none",
                rows=rows,
            )
        ]

    sections = _build_sections_from_markers(table_index, rows, markers)
    with_headers: list[LogicalSplit] = []
    for section in sections:
        section_rows = section.rows
        if section.start_row > 1:
            section_rows = header_rows + section_rows
        table_type = _note_segment_type(section_rows)
        with_headers.append(
            LogicalSplit(
                table_index=section.table_index,
                section_index=section.section_index,
                start_row=section.start_row,
                end_row=section.end_row,
                table_type=table_type,
                split_reason=section.split_reason,
                boundary_signal=section.boundary_signal,
                rows=section_rows,
            )
        )
    return with_headers


def _build_sections_from_markers(
    table_index: int,
    rows: list[list[str]],
    markers: list[tuple[int, str, str, str]],
) -> list[LogicalSplit]:
    unique_markers: list[tuple[int, str, str, str]] = []
    seen_indexes: set[int] = set()
    for marker in sorted(markers, key=lambda item: item[0]):
        if marker[0] in seen_indexes:
            continue
        seen_indexes.add(marker[0])
        unique_markers.append(marker)

    sections: list[LogicalSplit] = []
    for section_index, (start, table_type, reason, signal) in enumerate(unique_markers):
        end = (
            unique_markers[section_index + 1][0] - 1
            if section_index + 1 < len(unique_markers)
            else len(rows) - 1
        )
        section_rows = rows[start : end + 1]
        if not any(_row_text(row) for row in section_rows):
            continue
        sections.append(
            LogicalSplit(
                table_index=table_index,
                section_index=section_index,
                start_row=start,
                end_row=end,
                table_type=table_type,
                split_reason=reason,
                boundary_signal=signal,
                rows=section_rows,
            )
        )
    return sections


def _split_payload(
    *,
    extractor: CamelotTableExtractor,
    split: LogicalSplit,
    source_report_year: int,
    page_number: int,
    classified_table_types: list[str],
) -> dict[str, Any]:
    metric_values = extractor._extract_metric_values(
        rows=split.rows,
        source_report_year=source_report_year,
        page_number=page_number,
        table_type=split.table_type,
    )
    classified_scores = [
        {
            "table_type": table_type,
            "match_score": _table_type_match_score(split.rows, table_type),
        }
        for table_type in classified_table_types
    ]
    return {
        "section_index": split.section_index,
        "source_table_index": split.table_index,
        "start_row": split.start_row,
        "end_row": split.end_row,
        "row_count": len(split.rows),
        "column_count": max((len(row) for row in split.rows), default=0),
        "logical_table_type": split.table_type,
        "split_reason": split.split_reason,
        "boundary_signal": split.boundary_signal,
        "metric_values": len(metric_values),
        "classified_type_scores": classified_scores,
        "sample_rows": [_row_text(row) for row in split.rows[:8]],
    }


def _separability_signals(*, page_number: int, rows: list[list[str]]) -> dict[str, Any]:
    blank_rows = [index for index, row in enumerate(rows) if not _row_text(row)]
    heading_rows = []
    subtotal_rows = []
    year_header_rows = []
    note_reference_rows = []
    for index, row in enumerate(rows):
        text = _row_text(row)
        normalized = _normalize_text(text)
        compact = _compact(normalized)
        if "verticalanalysis" in compact or "horizontalanalysis" in compact:
            heading_rows.append({"row": index, "text": text})
        if page_number == 164 and index == 0 and "profit" in compact and "loss" in compact:
            heading_rows.append({"row": index, "text": text})
        if _contains_any(normalized, ("total", "gross profit", "net assets", "profit after", "total comprehensive")):
            subtotal_rows.append({"row": index, "text": text})
        if len(_years_in_row(row)) >= 2:
            year_header_rows.append({"row": index, "text": text})
        if _note_reference(text):
            note_reference_rows.append({"row": index, "text": text})
    return {
        "blank_rows": blank_rows,
        "heading_rows": heading_rows,
        "subtotal_rows": subtotal_rows[:20],
        "year_header_changes": year_header_rows,
        "note_reference_rows": note_reference_rows,
        "signals_supporting_split": _signals_supporting_split(
            heading_rows=heading_rows,
            year_header_rows=year_header_rows,
            note_reference_rows=note_reference_rows,
            blank_rows=blank_rows,
        ),
    }


def _signals_supporting_split(
    *,
    heading_rows: list[dict[str, Any]],
    year_header_rows: list[dict[str, Any]],
    note_reference_rows: list[dict[str, Any]],
    blank_rows: list[int],
) -> list[str]:
    signals: list[str] = []
    if heading_rows:
        signals.append("heading_rows")
    if year_header_rows:
        signals.append("year_header_changes")
    if note_reference_rows:
        signals.append("note_references")
    if blank_rows:
        signals.append("blank_rows")
    return signals


def _page_feasibility(page_number: int, splits: list[LogicalSplit]) -> dict[str, Any]:
    if page_number in {163, 164}:
        return {
            "table_splitting_practical": True,
            "multi_label_support_simpler": False,
            "neither_justified": False,
            "reason": (
                "Logical boundaries are explicit heading rows with year headers, "
                "so deterministic post-extraction splitting is practical."
            ),
        }
    if page_number == 321:
        return {
            "table_splitting_practical": True,
            "multi_label_support_simpler": True,
            "neither_justified": False,
            "reason": (
                "Note references create usable boundaries, but repeated nested "
                "investment, asset/liability, and profit/loss sections mean "
                "multi-label support is simpler for first production value."
            ),
        }
    return {
        "table_splitting_practical": False,
        "multi_label_support_simpler": False,
        "neither_justified": True,
        "reason": "No stable split signals were identified.",
    }


def _summary(pages: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "pages_audited": len(pages),
        "current_extracted_tables": sum(page["current_extracted_table_count"] for page in pages),
        "simulated_split_tables": sum(page["simulated_split_table_count"] for page in pages),
        "current_matched_tables": sum(
            page["current_matching"]["matched_table_count"] for page in pages
        ),
        "simulated_matched_classified_types": sum(
            page["simulated_matching"]["matched_classified_type_count"] for page in pages
        ),
        "estimated_additional_matched_tables": sum(
            page["estimated_impact"]["additional_matched_tables"] for page in pages
        ),
        "estimated_unmatched_classified_type_reduction": sum(
            page["estimated_impact"]["reduction_in_unmatched_classified_types"] for page in pages
        ),
        "estimated_unclassified_table_reduction": sum(
            page["estimated_impact"]["reduction_in_unclassified_tables"] for page in pages
        ),
        "metric_values_affected": sum(
            page["estimated_impact"]["metric_values_affected"] for page in pages
        ),
    }


def _recommendation(pages: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "overall": "hybrid",
        "answer": {
            "A_table_splitting_practical": True,
            "B_multi_label_support_simpler": True,
            "C_neither_justified": False,
        },
        "details": [
            "Pages 163 and 164 are strong candidates for deterministic table splitting because section headings and year-header rows are explicit.",
            "Page 321 can be split by note references, but the nested repeating note pattern makes multi-label support a simpler first production step.",
            "Splitting primarily reduces unmatched classified types; it does not materially reduce unclassified tables for these three pages because current tables are already assigned to at least one type.",
        ],
    }


def _primary_type_for_page(page_number: int) -> str:
    if page_number == 163:
        return "balance_sheet"
    if page_number == 164:
        return "income_statement"
    return UNCLASSIFIED_TABLE_TYPE


def _note_segment_type(rows: list[list[str]]) -> str:
    segment_text = "\n".join(_row_text(row) for row in rows)
    normalized = _normalize_text(segment_text)
    if _contains_any(normalized, ("profit or loss", "revenue", "cost of sales", "net profit")):
        return "income_statement"
    if _contains_any(normalized, ("assets", "liabilities", "net assets", "cash equivalents")):
        return "balance_sheet"
    if _contains_any(normalized, ("investment at cost", "share of cumulative profit", "foreign currency translation reserve")):
        return "investment_note"
    return "notes"


def _note_reference(text: str) -> bool:
    return re.match(r"^\s*\d{1,2}\.\d+(?:\.\d+)?\b", text) is not None


def _years_in_row(row: list[str]) -> list[int]:
    years: list[int] = []
    for cell in row:
        for match in re.findall(r"\b(20[0-9]{2}|19[0-9]{2})\b", str(cell)):
            years.append(int(match))
    return years


def _contains_any(text: str, phrases: tuple[str, ...]) -> bool:
    return any(_contains_phrase(text, phrase) for phrase in phrases)


def _row_text(row: list[str]) -> str:
    return " | ".join(str(cell).strip() for cell in row if str(cell).strip())


def _compact(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", value.lower())


def _configure_workspace_temp(output_dir: Path) -> None:
    temp_root = output_dir / ".table_splitting_tmp"
    temp_root.mkdir(parents=True, exist_ok=True)
    os.environ["TMP"] = str(temp_root)
    os.environ["TEMP"] = str(temp_root)
    tempfile.tempdir = str(temp_root)
    original_rmtree = shutil.rmtree

    def quiet_rmtree(path: str, *args: Any, **kwargs: Any) -> None:
        try:
            original_rmtree(path, *args, **kwargs)
        except PermissionError:
            return None

    shutil.rmtree = quiet_rmtree  # type: ignore[assignment]


if __name__ == "__main__":
    raise SystemExit(main())
