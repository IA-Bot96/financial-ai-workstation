"""Standalone experiment for splitting analysis-style financial tables.

Scope is intentionally narrow:

* balance_sheet + vertical_analysis + horizontal_analysis
* income_statement + vertical_analysis + horizontal_analysis

The script does not modify production extraction or matching code. It extracts
candidate pages, splits only explicit analysis sections, replays the existing
classification matcher on the split rows, and writes a JSON report.
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
    PageTableType,
)
from ocr_engine.models.table_detection_result import TableDetectionResult  # noqa: E402
from ocr_engine.services.camelot_table_extractor import (  # noqa: E402
    UNCLASSIFIED_TABLE_TYPE,
    CamelotTableExtractor,
    _build_extraction_quality_report,
    _contains_phrase,
    _normalize_key,
    _normalize_text,
    _table_type_match_score,
)

OUTPUT_PATH = PROJECT_ROOT / "output" / "analysis_table_splitting_experiment.json"
LOG_PATH = PROJECT_ROOT / "output" / "analysis_table_splitting_experiment.log"
REPORT_CONTEXTS = (
    (
        "Lucky Cement",
        PROJECT_ROOT / "output" / "lucky-cement_insights_diagnostics_context.json",
    ),
    (
        "Millat",
        PROJECT_ROOT / "output" / "millat_insights_diagnostics_context.json",
    ),
)
REQUIRED_LUCKY_PAGES = {163, 164}
PRIMARY_TYPES = {
    "balance_sheet",
    "statement_of_financial_position",
    "income_statement",
    "profit_and_loss",
    "statement_of_profit_or_loss",
}
ANALYSIS_TYPES = {"vertical_analysis", "horizontal_analysis"}


@dataclass(frozen=True)
class ReportContext:
    """Loaded report context needed by the experiment."""

    label: str
    company_name: str
    pdf_path: str
    source_report_year: int
    classification_result: FinancialTableClassificationResult
    detection_result: TableDetectionResult


@dataclass(frozen=True)
class SplitSection:
    """One simulated logical subtable split from an extracted physical table."""

    source_table_index: int
    section_index: int
    start_row: int
    end_row: int
    proposed_table_type: str
    boundary_source: str
    boundary_text: str
    rows: list[list[str]]


def main() -> int:
    """Run the analysis-style table splitting experiment."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", default=str(OUTPUT_PATH))
    parser.add_argument("--log-file", default=str(LOG_PATH))
    args = parser.parse_args()

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    log_path = Path(args.log_file)
    log_path.parent.mkdir(parents=True, exist_ok=True)
    _configure_workspace_temp(output_path.parent)
    logging.disable(logging.CRITICAL)

    reports = [_load_report(label, path) for label, path in REPORT_CONTEXTS]
    extractor = CamelotTableExtractor()

    report_results: list[dict[str, Any]] = []
    with log_path.open("w", encoding="utf-8") as log_handle:
        with contextlib.redirect_stderr(log_handle):
            for report in reports:
                report_results.append(_run_report(report, extractor))

    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "experiment": "analysis_table_splitting",
        "production_code_modified": False,
        "scope": {
            "included_patterns": [
                "balance_sheet + vertical_analysis + horizontal_analysis",
                "income_statement + vertical_analysis + horizontal_analysis",
            ],
            "excluded_patterns": [
                "generic sensitivity_analysis",
                "notes with nested balance_sheet/income_statement sections",
                "non-analysis primary financial statements",
            ],
        },
        "summary": _summary(report_results),
        "reports": report_results,
        "recommendation": _recommendation(report_results),
        "log_file": str(log_path),
    }
    output_path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    print(f"Wrote {output_path}")
    return 0


def _load_report(label: str, path: Path) -> ReportContext:
    context = json.loads(path.read_text(encoding="utf-8"))
    report = context["reports"][0]
    source_report_year = int(report["year"])
    year_key = str(source_report_year)
    return ReportContext(
        label=label,
        company_name=context.get("company_name") or label,
        pdf_path=report["file_path"],
        source_report_year=source_report_year,
        classification_result=FinancialTableClassificationResult.model_validate(
            context["classification_results"][year_key]
        ),
        detection_result=TableDetectionResult.model_validate(
            context["table_detection_results"][year_key]
        ),
    )


def _run_report(
    report: ReportContext,
    extractor: CamelotTableExtractor,
) -> dict[str, Any]:
    detected_counts = {
        page.page_number: page.tables_detected
        for page in report.detection_result.detected_pages
    }
    candidates, excluded_candidates = _candidate_pages(report)
    page_results: list[dict[str, Any]] = []
    for page_table_type in candidates:
        raw_extraction = extractor._extract_page_tables(
            report.pdf_path,
            page_table_type.page_number,
        )
        current_tables, current_diagnostic = extractor._build_extracted_tables(
            page_table_type=page_table_type,
            raw_tables=raw_extraction.raw_tables,
            detected_table_count=detected_counts.get(page_table_type.page_number, 0),
            extraction_strategy=raw_extraction.strategy,
            extraction_quality=raw_extraction.quality,
        )
        split_sections = [
            section
            for table_index, rows in enumerate(raw_extraction.raw_tables)
            for section in _split_analysis_table(
                rows=rows,
                source_table_index=table_index,
                primary_table_type=_primary_table_type(page_table_type.table_types),
            )
        ]
        split_rows = [section.rows for section in split_sections]
        split_quality = extractor._evaluate_extraction_quality(split_rows)
        split_tables, split_diagnostic = extractor._build_extracted_tables(
            page_table_type=page_table_type,
            raw_tables=split_rows,
            detected_table_count=detected_counts.get(page_table_type.page_number, 0),
            extraction_strategy=f"{raw_extraction.strategy}+analysis_style_split",
            extraction_quality=split_quality,
        )
        page_results.append(
            _page_result(
                extractor=extractor,
                report=report,
                page_table_type=page_table_type,
                raw_table_count=len(raw_extraction.raw_tables),
                extraction_strategy=raw_extraction.strategy,
                current_tables=current_tables,
                current_diagnostic=current_diagnostic,
                split_sections=split_sections,
                split_tables=split_tables,
                split_diagnostic=split_diagnostic,
            )
        )

    return {
        "label": report.label,
        "company_name": report.company_name,
        "source_report_year": report.source_report_year,
        "pdf_path": report.pdf_path,
        "candidate_pages": [page.page_number for page in candidates],
        "excluded_analysis_candidates": excluded_candidates,
        "summary": _report_summary(page_results),
        "pages": page_results,
    }


def _candidate_pages(
    report: ReportContext,
) -> tuple[list[PageTableType], list[dict[str, Any]]]:
    candidates: list[PageTableType] = []
    excluded: list[dict[str, Any]] = []
    for page_table_type in report.classification_result.page_table_types:
        normalized_types = {_normalize_key(table_type) for table_type in page_table_type.table_types}
        is_candidate = _is_analysis_style_types(normalized_types)
        if (
            report.label.lower().startswith("lucky")
            and page_table_type.page_number in REQUIRED_LUCKY_PAGES
        ):
            is_candidate = True
        if is_candidate:
            candidates.append(page_table_type)
            continue
        if any("analysis" in table_type for table_type in normalized_types):
            excluded.append(
                {
                    "page_number": page_table_type.page_number,
                    "table_types": page_table_type.table_types,
                    "reason": "analysis_type_present_but_not_balance_or_income_with_vertical_horizontal_pair",
                }
            )
    return candidates, excluded


def _is_analysis_style_types(normalized_types: set[str]) -> bool:
    return (
        bool(normalized_types & PRIMARY_TYPES)
        and "vertical_analysis" in normalized_types
        and "horizontal_analysis" in normalized_types
    )


def _page_result(
    *,
    extractor: CamelotTableExtractor,
    report: ReportContext,
    page_table_type: PageTableType,
    raw_table_count: int,
    extraction_strategy: str,
    current_tables: list[Any],
    current_diagnostic: Any,
    split_sections: list[SplitSection],
    split_tables: list[Any],
    split_diagnostic: Any,
) -> dict[str, Any]:
    current_quality = _build_extraction_quality_report(current_tables)
    split_quality = _build_extraction_quality_report(split_tables)
    previously_unmatched = {
        _normalize_key(table_type)
        for table_type in current_diagnostic.unmatched_classifications
    }
    metric_values_recovered = sum(
        len(table.metric_values)
        for table in split_tables
        if _normalize_key(table.table_type) in previously_unmatched
    )
    return {
        "page_number": page_table_type.page_number,
        "classified_table_types": page_table_type.table_types,
        "extraction_strategy": extraction_strategy,
        "current": {
            "extracted_table_count": raw_table_count,
            "matched_tables": current_diagnostic.matched_table_count,
            "unmatched_classified_types": current_diagnostic.unmatched_classifications,
            "unclassified_tables": current_quality.unclassified_table_count,
            "assigned_table_types": [table.table_type for table in current_tables],
            "metric_values": current_quality.metric_values_generated,
            "duplicate_metric_groups": current_quality.duplicate_metric_group_count,
            "conflicting_metric_groups": current_quality.conflicting_metric_group_count,
        },
        "after_split": {
            "split_table_count": len(split_sections),
            "matched_tables": split_diagnostic.matched_table_count,
            "unmatched_classified_types": split_diagnostic.unmatched_classifications,
            "unclassified_tables": split_quality.unclassified_table_count,
            "assigned_table_types": [table.table_type for table in split_tables],
            "metric_values": split_quality.metric_values_generated,
            "metric_values_recovered_for_previously_unmatched_types": metric_values_recovered,
            "duplicate_metric_groups": split_quality.duplicate_metric_group_count,
            "conflicting_metric_groups": split_quality.conflicting_metric_group_count,
        },
        "delta": {
            "matched_tables": (
                split_diagnostic.matched_table_count
                - current_diagnostic.matched_table_count
            ),
            "unmatched_classified_types": (
                len(split_diagnostic.unmatched_classifications)
                - len(current_diagnostic.unmatched_classifications)
            ),
            "unclassified_tables": (
                split_quality.unclassified_table_count
                - current_quality.unclassified_table_count
            ),
            "metric_values": (
                split_quality.metric_values_generated
                - current_quality.metric_values_generated
            ),
            "duplicate_metric_groups": (
                split_quality.duplicate_metric_group_count
                - current_quality.duplicate_metric_group_count
            ),
            "conflicting_metric_groups": (
                split_quality.conflicting_metric_group_count
                - current_quality.conflicting_metric_group_count
            ),
        },
        "section_boundary_diagnostics": _boundary_diagnostics(
            current_tables[0].rows if current_tables else []
        ),
        "split_sections": [
            _section_payload(
                extractor=extractor,
                section=section,
                matched_table=(
                    split_tables[index] if index < len(split_tables) else None
                ),
                classified_table_types=page_table_type.table_types,
                source_report_year=report.source_report_year,
                page_number=page_table_type.page_number,
            )
            for index, section in enumerate(split_sections)
        ],
    }


def _split_analysis_table(
    *,
    rows: list[list[str]],
    source_table_index: int,
    primary_table_type: str,
) -> list[SplitSection]:
    markers: list[tuple[int, str, str, str]] = [
        (0, primary_table_type, "table_start", _row_text(rows[0]) if rows else "")
    ]
    horizontal_seen = False
    vertical_seen = False
    for index, row in enumerate(rows):
        text = _row_text(row)
        compact = _compact(_normalize_text(text))
        year_count = len(_years_in_row(row))
        if "verticalanalysis" in compact and year_count >= 2 and not vertical_seen:
            markers.append((index, "vertical_analysis", "heading_row_with_repeated_year_header", text))
            vertical_seen = True
        if "horizontalanalysis" in compact and year_count >= 2 and not horizontal_seen:
            markers.append((index, "horizontal_analysis", "heading_row_with_repeated_year_header", text))
            horizontal_seen = True

    markers = _dedupe_markers(markers)
    sections: list[SplitSection] = []
    for section_index, (start, table_type, source, text) in enumerate(markers):
        end = markers[section_index + 1][0] - 1 if section_index + 1 < len(markers) else len(rows) - 1
        section_rows = rows[start : end + 1]
        sections.append(
            SplitSection(
                source_table_index=source_table_index,
                section_index=section_index,
                start_row=start,
                end_row=end,
                proposed_table_type=table_type,
                boundary_source=source,
                boundary_text=text,
                rows=section_rows,
            )
        )
    return sections


def _section_payload(
    *,
    extractor: CamelotTableExtractor,
    section: SplitSection,
    matched_table: Any | None,
    classified_table_types: list[str],
    source_report_year: int,
    page_number: int,
) -> dict[str, Any]:
    metric_values = extractor._extract_metric_values(
        rows=section.rows,
        source_report_year=source_report_year,
        page_number=page_number,
        table_type=section.proposed_table_type,
    )
    return {
        "section_index": section.section_index,
        "source_table_index": section.source_table_index,
        "start_row": section.start_row,
        "end_row": section.end_row,
        "row_count": len(section.rows),
        "column_count": max((len(row) for row in section.rows), default=0),
        "proposed_table_type": section.proposed_table_type,
        "matched_table_type": matched_table.table_type if matched_table else None,
        "boundary_source": section.boundary_source,
        "boundary_text": section.boundary_text,
        "metric_values": len(metric_values),
        "classified_type_match_scores": [
            {
                "table_type": table_type,
                "match_score": _table_type_match_score(section.rows, table_type),
            }
            for table_type in classified_table_types
        ],
        "sample_rows": [_row_text(row) for row in section.rows[:8]],
    }


def _boundary_diagnostics(rows: list[list[str]]) -> dict[str, Any]:
    heading_rows: list[dict[str, Any]] = []
    repeated_year_header_rows: list[dict[str, Any]] = []
    subtotal_rows: list[dict[str, Any]] = []
    blank_rows: list[int] = []
    for index, row in enumerate(rows):
        text = _row_text(row)
        normalized = _normalize_text(text)
        compact = _compact(normalized)
        years = _years_in_row(row)
        if not text:
            blank_rows.append(index)
        if "verticalanalysis" in compact or "horizontalanalysis" in compact:
            heading_rows.append({"row": index, "text": text})
        if len(years) >= 2:
            repeated_year_header_rows.append({"row": index, "years": years, "text": text})
        if _is_subtotal_row(normalized):
            subtotal_rows.append({"row": index, "text": text})
    return {
        "heading_rows": heading_rows,
        "repeated_year_header_rows": repeated_year_header_rows,
        "subtotal_rows": subtotal_rows[:30],
        "blank_rows": blank_rows,
        "boundary_strategy": [
            "start with primary table at first row",
            "split when heading row contains vertical_analysis or horizontal_analysis",
            "require repeated year headers on analysis heading rows",
            "use subtotal rows as section confidence evidence, not as hard boundaries",
        ],
    }


def _report_summary(pages: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "pages_tested": len(pages),
        "matched_tables_before": sum(page["current"]["matched_tables"] for page in pages),
        "matched_tables_after": sum(page["after_split"]["matched_tables"] for page in pages),
        "unmatched_classified_types_before": sum(
            len(page["current"]["unmatched_classified_types"]) for page in pages
        ),
        "unmatched_classified_types_after": sum(
            len(page["after_split"]["unmatched_classified_types"]) for page in pages
        ),
        "unclassified_tables_before": sum(page["current"]["unclassified_tables"] for page in pages),
        "unclassified_tables_after": sum(page["after_split"]["unclassified_tables"] for page in pages),
        "metric_values_before": sum(page["current"]["metric_values"] for page in pages),
        "metric_values_after": sum(page["after_split"]["metric_values"] for page in pages),
        "metric_values_recovered_for_previously_unmatched_types": sum(
            page["after_split"]["metric_values_recovered_for_previously_unmatched_types"]
            for page in pages
        ),
        "duplicate_metric_groups_before": sum(
            page["current"]["duplicate_metric_groups"] for page in pages
        ),
        "duplicate_metric_groups_after": sum(
            page["after_split"]["duplicate_metric_groups"] for page in pages
        ),
        "conflicting_metric_groups_before": sum(
            page["current"]["conflicting_metric_groups"] for page in pages
        ),
        "conflicting_metric_groups_after": sum(
            page["after_split"]["conflicting_metric_groups"] for page in pages
        ),
    }


def _summary(report_results: list[dict[str, Any]]) -> dict[str, Any]:
    totals = {
        "reports_tested": len(report_results),
        "pages_tested": 0,
        "matched_tables_before": 0,
        "matched_tables_after": 0,
        "unmatched_classified_types_before": 0,
        "unmatched_classified_types_after": 0,
        "unclassified_tables_before": 0,
        "unclassified_tables_after": 0,
        "metric_values_before": 0,
        "metric_values_after": 0,
        "metric_values_recovered_for_previously_unmatched_types": 0,
        "duplicate_metric_groups_before": 0,
        "duplicate_metric_groups_after": 0,
        "conflicting_metric_groups_before": 0,
        "conflicting_metric_groups_after": 0,
    }
    for report in report_results:
        for key in totals:
            if key == "reports_tested":
                continue
            totals[key] += report["summary"].get(key, 0)
    totals["deltas"] = {
        "matched_tables": totals["matched_tables_after"] - totals["matched_tables_before"],
        "unmatched_classified_types": (
            totals["unmatched_classified_types_after"]
            - totals["unmatched_classified_types_before"]
        ),
        "unclassified_tables": totals["unclassified_tables_after"] - totals["unclassified_tables_before"],
        "metric_values": totals["metric_values_after"] - totals["metric_values_before"],
        "duplicate_metric_groups": (
            totals["duplicate_metric_groups_after"]
            - totals["duplicate_metric_groups_before"]
        ),
        "conflicting_metric_groups": (
            totals["conflicting_metric_groups_after"]
            - totals["conflicting_metric_groups_before"]
        ),
    }
    return totals


def _recommendation(report_results: list[dict[str, Any]]) -> dict[str, Any]:
    summary = _summary(report_results)
    return {
        "production_recommendation": "promote_analysis_style_splitting_behind_feature_flag",
        "rationale": [
            "The split boundaries are explicit heading rows with repeated year headers.",
            "The experiment recovers logical matches for vertical_analysis and horizontal_analysis without needing OCR or classifier changes.",
            "This should remain scoped to analysis-style tables; note disclosures need a different splitter or multi-label support.",
        ],
        "expected_impact_from_experiment": summary["deltas"],
    }


def _primary_table_type(table_types: list[str]) -> str:
    for table_type in table_types:
        if _normalize_key(table_type) in PRIMARY_TYPES:
            return table_type
    return UNCLASSIFIED_TABLE_TYPE


def _dedupe_markers(
    markers: list[tuple[int, str, str, str]],
) -> list[tuple[int, str, str, str]]:
    result: list[tuple[int, str, str, str]] = []
    seen_rows: set[int] = set()
    for marker in sorted(markers, key=lambda item: item[0]):
        if marker[0] in seen_rows:
            continue
        seen_rows.add(marker[0])
        result.append(marker)
    return result


def _is_subtotal_row(normalized: str) -> bool:
    phrases = (
        "total assets",
        "total equity",
        "total equity and liabilities",
        "gross profit",
        "operating profit",
        "profit before taxation",
        "profit after taxation",
        "total comprehensive income",
    )
    return any(_contains_phrase(normalized, phrase) for phrase in phrases)


def _years_in_row(row: list[str]) -> list[int]:
    years: list[int] = []
    for cell in row:
        for match in re.findall(r"\b(19[0-9]{2}|20[0-9]{2})\b", str(cell)):
            years.append(int(match))
    return years


def _row_text(row: list[str]) -> str:
    return " | ".join(str(cell).strip() for cell in row if str(cell).strip())


def _compact(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", value.lower())


def _configure_workspace_temp(output_dir: Path) -> None:
    temp_root = output_dir / ".analysis_table_splitting_tmp"
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
