"""Standalone classifier-tightening experiment for OCR table classifications.

This script does not modify the production OCR pipeline. It replays the current
extraction/table-matching path with a stricter, rule-based post-classification
filter so we can quantify whether obvious primary-statement false positives are
driving unmatched classifications and unclassified extracted tables.
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
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

PROJECT_ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = PROJECT_ROOT / "backend"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from ocr_engine.models.financial_table_classification import (  # noqa: E402
    FinancialTableClassificationResult,
    PageTableType,
)
from ocr_engine.models.table_detection_result import TableDetectionResult  # noqa: E402
from ocr_engine.models.table_extraction import ExtractedTable  # noqa: E402
from ocr_engine.services.camelot_table_extractor import (  # noqa: E402
    UNCLASSIFIED_TABLE_TYPE,
    CamelotTableExtractor,
    _RawExtractionResult,
    _build_extraction_quality_report,
    _contains_phrase,
    _keywords_for_table_type,
    _normalize_key,
    _normalize_text,
    _table_type_match_score,
)

FOCUS_PAGES = {162, 271, 356}
DEFAULT_REPORTS = (
    (
        "Lucky Cement",
        PROJECT_ROOT / "output" / "lucky-cement_insights_diagnostics_context.json",
    ),
    (
        "Millat",
        PROJECT_ROOT / "output" / "millat_insights_diagnostics_context.json",
    ),
)

PRIMARY_STATEMENT_TYPES = {
    "income_statement",
    "profit_and_loss",
    "statement_of_profit_or_loss",
    "cash_flow_statement",
    "cash_flow",
    "statement_of_cash_flows",
}

NOTE_CONTEXT_MARKERS = (
    "notes to the financial statements",
    "note",
    "distribution costs",
    "administrative expenses",
    "cash generated from operations",
    "cash generated from operating activities",
)

SUPPORTING_SCHEDULE_MARKERS = (
    "distribution costs",
    "administrative expenses",
    "selling and distribution",
    "cost of sales",
    "cash generated from operations",
    "cash generated from operating activities",
)

FINANCIAL_HIGHLIGHTS_MARKERS = (
    "financial position",
    "turnover and profit",
    "turnover profit",
    "cash flow summary",
    "assets employed",
    "financed by",
)

INCOME_STATEMENT_FORMAL_HEADINGS = (
    "statement of profit or loss",
    "statement of comprehensive income",
    "income statement",
    "profit and loss account",
    "of profit or loss",
    "profit or loss",
)

CASH_FLOW_FORMAL_HEADINGS = (
    "statement of cash flows",
    "statement of cash flow",
    "cash flow statement",
)

BALANCE_SHEET_FORMAL_HEADINGS = (
    "statement of financial position",
    "financial position",
    "balance sheet",
)


@dataclass(frozen=True)
class ReportInputs:
    """Loaded report context required for a replay run."""

    label: str
    company_name: str
    pdf_path: str
    source_report_year: int
    classification_result: FinancialTableClassificationResult
    detection_result: TableDetectionResult


@dataclass(frozen=True)
class PageReplaySource:
    """Raw extraction data reused for original and tightened replay variants."""

    page_table_type: PageTableType
    raw_extraction: _RawExtractionResult
    detected_table_count: int


@dataclass(frozen=True)
class TighteningDecision:
    """Decision for one classified table type under the experimental rules."""

    table_type: str
    action: str
    reasons: tuple[str, ...]
    matched_keywords: tuple[str, ...]
    pre_tightening_match_score: int


def main() -> int:
    """Run the classifier-tightening replay experiment."""

    parser = argparse.ArgumentParser(
        description="Replay table classification with stricter primary-statement rules."
    )
    parser.add_argument(
        "--output",
        default=str(PROJECT_ROOT / "output" / "classifier_tightening_experiment.json"),
        help="Path for the JSON experiment report.",
    )
    parser.add_argument(
        "--log-file",
        default=str(PROJECT_ROOT / "output" / "classifier_tightening_experiment.log"),
        help="Path for verbose extraction logs emitted during replay.",
    )
    parser.add_argument(
        "--context",
        action="append",
        default=[],
        help=(
            "Optional context spec in the form Label=path/to/context.json. "
            "When omitted, Lucky Cement and Millat latest diagnostic contexts are used."
        ),
    )
    args = parser.parse_args()

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    log_path = Path(args.log_file)
    log_path.parent.mkdir(parents=True, exist_ok=True)
    temp_root = output_path.parent / ".classifier_tightening_tmp"
    temp_root.mkdir(parents=True, exist_ok=True)
    os.environ["TMP"] = str(temp_root)
    os.environ["TEMP"] = str(temp_root)
    tempfile.tempdir = str(temp_root)
    _suppress_temp_cleanup_permission_errors()

    logging.disable(logging.CRITICAL)
    reports = _load_reports(args.context)
    extractor = CamelotTableExtractor()

    report_results: list[dict[str, Any]] = []
    with log_path.open("w", encoding="utf-8") as log_handle:
        with contextlib.redirect_stderr(log_handle):
            for report in reports:
                print(f"Replaying {report.label} ({report.source_report_year})...")
                report_results.append(_replay_report(report, extractor))

    focus_traces = [
        trace
        for report_result in report_results
        for trace in report_result["focus_page_traces"]
    ]
    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "experiment": "classifier_tightening",
        "scope": {
            "production_code_modified": False,
            "focus_pages": sorted(FOCUS_PAGES),
            "reports_replayed": [
                {
                    "label": report.label,
                    "company_name": report.company_name,
                    "source_report_year": report.source_report_year,
                    "pdf_path": report.pdf_path,
                }
                for report in reports
            ],
        },
        "observed_root_causes": _observed_root_causes(focus_traces),
        "proposed_stricter_rules": _proposed_rules(),
        "reports": report_results,
        "summary": _summarize_reports(report_results),
        "focus_page_traces": focus_traces,
        "log_file": str(log_path),
    }
    output_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Wrote {output_path}")
    return 0


def _suppress_temp_cleanup_permission_errors() -> None:
    """Quiet Windows temp cleanup noise from PDF extraction dependencies."""

    original_rmtree = shutil.rmtree

    def quiet_rmtree(path: str, *args: Any, **kwargs: Any) -> None:
        try:
            original_rmtree(path, *args, **kwargs)
        except PermissionError:
            return None

    shutil.rmtree = quiet_rmtree  # type: ignore[assignment]


def _load_reports(context_specs: list[str]) -> list[ReportInputs]:
    specs: list[tuple[str, Path]]
    if context_specs:
        specs = []
        for spec in context_specs:
            if "=" not in spec:
                raise ValueError(f"Invalid --context spec: {spec!r}")
            label, raw_path = spec.split("=", 1)
            specs.append((label.strip(), Path(raw_path).resolve()))
    else:
        specs = list(DEFAULT_REPORTS)

    reports: list[ReportInputs] = []
    for label, path in specs:
        context = json.loads(path.read_text(encoding="utf-8"))
        report = context["reports"][0]
        year = str(report["year"])
        reports.append(
            ReportInputs(
                label=label,
                company_name=context.get("company_name") or label,
                pdf_path=report["file_path"],
                source_report_year=int(year),
                classification_result=FinancialTableClassificationResult.model_validate(
                    context["classification_results"][year]
                ),
                detection_result=TableDetectionResult.model_validate(
                    context["table_detection_results"][year]
                ),
            )
        )
    return reports


def _replay_report(
    report: ReportInputs,
    extractor: CamelotTableExtractor,
) -> dict[str, Any]:
    detected_counts = {
        detected_page.page_number: detected_page.tables_detected
        for detected_page in report.detection_result.detected_pages
    }
    page_sources: list[PageReplaySource] = []
    for page_table_type in report.classification_result.page_table_types:
        raw_extraction = extractor._extract_page_tables(
            report.pdf_path,
            page_table_type.page_number,
        )
        page_sources.append(
            PageReplaySource(
                page_table_type=page_table_type,
                raw_extraction=raw_extraction,
                detected_table_count=detected_counts.get(
                    page_table_type.page_number,
                    0,
                ),
            )
        )

    original = _run_variant(
        report=report,
        extractor=extractor,
        page_sources=page_sources,
        use_tightened_classifications=False,
    )
    tightened = _run_variant(
        report=report,
        extractor=extractor,
        page_sources=page_sources,
        use_tightened_classifications=True,
    )

    focus_traces = _focus_page_traces(report, extractor, page_sources)
    return {
        "label": report.label,
        "company_name": report.company_name,
        "source_report_year": report.source_report_year,
        "pdf_path": report.pdf_path,
        "original": original,
        "tightened": tightened,
        "delta": _variant_delta(original, tightened),
        "classification_changes": _classification_changes(page_sources),
        "focus_page_traces": focus_traces,
    }


def _run_variant(
    *,
    report: ReportInputs,
    extractor: CamelotTableExtractor,
    page_sources: list[PageReplaySource],
    use_tightened_classifications: bool,
) -> dict[str, Any]:
    tables: list[ExtractedTable] = []
    page_rows: list[dict[str, Any]] = []
    removed_classifications: Counter[str] = Counter()
    added_classifications: Counter[str] = Counter()

    for source in page_sources:
        page_table_type = source.page_table_type
        decisions = _tightening_decisions(
            page_table_type.table_types,
            source.raw_extraction.raw_tables,
        )
        if use_tightened_classifications:
            tightened_types = _tightened_table_types(page_table_type.table_types, decisions)
            for removed in set(page_table_type.table_types) - set(tightened_types):
                removed_classifications[removed] += 1
            for added in set(tightened_types) - set(page_table_type.table_types):
                added_classifications[added] += 1
            page_table_type = PageTableType(
                year=page_table_type.year,
                page_number=page_table_type.page_number,
                table_types=tightened_types,
            )

        page_tables, diagnostic = extractor._build_extracted_tables(
            page_table_type=page_table_type,
            raw_tables=source.raw_extraction.raw_tables,
            detected_table_count=source.detected_table_count,
            extraction_strategy=source.raw_extraction.strategy,
            extraction_quality=source.raw_extraction.quality,
        )
        tables.extend(page_tables)
        page_rows.append(
            {
                "page_number": page_table_type.page_number,
                "detected_table_count": diagnostic.detected_table_count,
                "classified_table_count": diagnostic.classified_table_count,
                "extracted_table_count": diagnostic.extracted_table_count,
                "matched_table_count": diagnostic.matched_table_count,
                "unmatched_classifications": diagnostic.unmatched_classifications,
                "unmatched_extractions": diagnostic.unmatched_extractions,
                "table_types": page_table_type.table_types,
            }
        )

    quality_report = _build_extraction_quality_report(tables)
    metric_values = [metric_value for table in tables for metric_value in table.metric_values]
    total_classified = sum(len(row["table_types"]) for row in page_rows)
    total_extracted = sum(row["extracted_table_count"] for row in page_rows)
    total_matched = sum(row["matched_table_count"] for row in page_rows)
    unmatched_classifications = [
        f"page={row['page_number']} table_type={table_type}"
        for row in page_rows
        for table_type in row["unmatched_classifications"]
    ]
    unmatched_extractions = [
        f"page={row['page_number']} table_index={table_index}"
        for row in page_rows
        for table_index in row["unmatched_extractions"]
    ]
    return {
        "total_detected_tables": sum(source.detected_table_count for source in page_sources),
        "total_classified_tables": total_classified,
        "total_extracted_tables": total_extracted,
        "total_matched_tables": total_matched,
        "unmatched_classified_types": len(unmatched_classifications),
        "unclassified_tables": quality_report.unclassified_table_count,
        "metric_values_generated": len(metric_values),
        "duplicate_metric_groups": quality_report.duplicate_metric_group_count,
        "conflicting_metric_groups": quality_report.conflicting_metric_group_count,
        "tables_rejected": quality_report.tables_rejected,
        "missing_year_tables": quality_report.missing_year_table_count,
        "missing_label_tables": quality_report.missing_label_table_count,
        "removed_classifications": dict(sorted(removed_classifications.items())),
        "added_classifications": dict(sorted(added_classifications.items())),
        "top_unmatched_classifications": _top_unmatched(unmatched_classifications),
        "pages_with_mismatched_counts": [
            row
            for row in page_rows
            if row["classified_table_count"] != row["extracted_table_count"]
        ][:30],
        "unmatched_extraction_examples": unmatched_extractions[:50],
    }


def _tightening_decisions(
    table_types: list[str],
    raw_tables: list[list[list[str]]],
) -> list[TighteningDecision]:
    table_text = _page_table_text(raw_tables)
    normalized_text = _normalize_text(table_text)
    compact_text = _compact(normalized_text)
    decisions: list[TighteningDecision] = []
    for table_type in table_types:
        normalized_type = _normalize_key(table_type)
        matched_keywords = _matched_keywords(normalized_text, table_type)
        score = sum(
            _table_type_match_score(rows, table_type)
            for rows in raw_tables
        )
        keep, reasons = _should_keep_table_type(
            normalized_type=normalized_type,
            normalized_text=normalized_text,
            compact_text=compact_text,
            all_table_types=table_types,
        )
        decisions.append(
            TighteningDecision(
                table_type=table_type,
                action="keep" if keep else "remove",
                reasons=tuple(reasons),
                matched_keywords=tuple(matched_keywords),
                pre_tightening_match_score=score,
            )
        )
    return decisions


def _should_keep_table_type(
    *,
    normalized_type: str,
    normalized_text: str,
    compact_text: str,
    all_table_types: list[str],
) -> tuple[bool, list[str]]:
    reasons: list[str] = []
    note_context = _has_note_context(normalized_text, compact_text)
    financial_highlights_context = _has_any_loose(
        normalized_text,
        compact_text,
        FINANCIAL_HIGHLIGHTS_MARKERS,
    )
    supporting_schedule_context = _has_any_loose(
        normalized_text,
        compact_text,
        SUPPORTING_SCHEDULE_MARKERS,
    )
    formal_income_statement = _has_any_loose(
        normalized_text,
        compact_text,
        INCOME_STATEMENT_FORMAL_HEADINGS,
    )
    formal_cash_flow_statement = _has_any_loose(
        normalized_text,
        compact_text,
        CASH_FLOW_FORMAL_HEADINGS,
    )
    formal_balance_sheet = _has_any_loose(
        normalized_text,
        compact_text,
        BALANCE_SHEET_FORMAL_HEADINGS,
    )

    if normalized_type in {"income_statement", "profit_and_loss", "statement_of_profit_or_loss"}:
        if supporting_schedule_context and not formal_income_statement:
            reasons.append("supporting_schedule_not_primary_income_statement")
        if note_context and not formal_income_statement:
            reasons.append("note_context_without_formal_income_statement_heading")
        if (
            financial_highlights_context
            and formal_balance_sheet
            and not formal_income_statement
        ):
            reasons.append("financial_highlights_table_not_primary_income_statement")
        return not reasons, reasons or ["formal_or_non_note_income_statement_signal"]

    if normalized_type in {"cash_flow_statement", "cash_flow", "statement_of_cash_flows"}:
        if _has_any_loose(
            normalized_text,
            compact_text,
            ("cash generated from operations", "cash generated from operating activities"),
        ) and not formal_cash_flow_statement:
            reasons.append("cash_generated_from_operations_note_not_cash_flow_statement")
        if note_context and not formal_cash_flow_statement:
            reasons.append("note_context_without_formal_cash_flow_heading")
        if financial_highlights_context and not formal_cash_flow_statement:
            reasons.append("financial_highlights_table_not_primary_cash_flow_statement")
        return not reasons, reasons or ["formal_or_non_note_cash_flow_signal"]

    # Do not tighten balance_sheet yet; it is the correct label on the focus page
    # and removing it would hide the classifier behavior being measured here.
    if normalized_type in {"balance_sheet", "statement_of_financial_position"}:
        return True, ["balance_sheet_tightening_not_part_of_experiment"]

    return True, ["non_primary_statement_type_preserved"]


def _tightened_table_types(
    original_types: list[str],
    decisions: list[TighteningDecision],
) -> list[str]:
    tightened = [
        decision.table_type
        for decision in decisions
        if decision.action == "keep"
    ]
    removed_primary_in_note = any(
        decision.action == "remove"
        and (
            "note_context_without_formal_income_statement_heading" in decision.reasons
            or "note_context_without_formal_cash_flow_heading" in decision.reasons
            or "supporting_schedule_not_primary_income_statement" in decision.reasons
            or "cash_generated_from_operations_note_not_cash_flow_statement" in decision.reasons
        )
        for decision in decisions
    )
    if removed_primary_in_note and "notes" not in {
        _normalize_key(table_type) for table_type in tightened
    }:
        tightened.append("notes")
    if not tightened:
        # Keep the first original type instead of making the page disappear.
        # The report explicitly marks this as a rule that needs human review.
        return original_types[:1]
    return _dedupe_preserve_order(tightened)


def _focus_page_traces(
    report: ReportInputs,
    extractor: CamelotTableExtractor,
    page_sources: list[PageReplaySource],
) -> list[dict[str, Any]]:
    traces: list[dict[str, Any]] = []
    for source in page_sources:
        page_number = source.page_table_type.page_number
        if page_number not in FOCUS_PAGES:
            continue
        original_types = source.page_table_type.table_types
        decisions = _tightening_decisions(original_types, source.raw_extraction.raw_tables)
        tightened_types = _tightened_table_types(original_types, decisions)
        original_tables, original_diagnostic = extractor._build_extracted_tables(
            page_table_type=source.page_table_type,
            raw_tables=source.raw_extraction.raw_tables,
            detected_table_count=source.detected_table_count,
            extraction_strategy=source.raw_extraction.strategy,
            extraction_quality=source.raw_extraction.quality,
        )
        tightened_page_table_type = PageTableType(
            year=source.page_table_type.year,
            page_number=page_number,
            table_types=tightened_types,
        )
        tightened_tables, tightened_diagnostic = extractor._build_extracted_tables(
            page_table_type=tightened_page_table_type,
            raw_tables=source.raw_extraction.raw_tables,
            detected_table_count=source.detected_table_count,
            extraction_strategy=source.raw_extraction.strategy,
            extraction_quality=source.raw_extraction.quality,
        )
        text = _page_table_text(source.raw_extraction.raw_tables)
        traces.append(
            {
                "report": report.label,
                "company_name": report.company_name,
                "page_number": page_number,
                "detected_table_count": source.detected_table_count,
                "extraction_strategy": source.raw_extraction.strategy,
                "raw_extracted_table_count": len(source.raw_extraction.raw_tables),
                "original_classified_types": original_types,
                "tightened_classified_types": tightened_types,
                "removed_classified_types": [
                    table_type
                    for table_type in original_types
                    if _normalize_key(table_type)
                    not in {_normalize_key(value) for value in tightened_types}
                ],
                "page_signals": _page_signals(text),
                "type_decisions": [_decision_payload(decision) for decision in decisions],
                "original_matching": _matching_payload(original_tables, original_diagnostic),
                "tightened_matching": _matching_payload(tightened_tables, tightened_diagnostic),
                "extracted_text_sample": text[:2500],
            }
        )
    return traces


def _decision_payload(decision: TighteningDecision) -> dict[str, Any]:
    return {
        "table_type": decision.table_type,
        "action": decision.action,
        "reasons": list(decision.reasons),
        "matched_keywords": list(decision.matched_keywords),
        "pre_tightening_match_score": decision.pre_tightening_match_score,
    }


def _matching_payload(tables: list[ExtractedTable], diagnostic: Any) -> dict[str, Any]:
    return {
        "classified_table_count": diagnostic.classified_table_count,
        "extracted_table_count": diagnostic.extracted_table_count,
        "matched_table_count": diagnostic.matched_table_count,
        "unmatched_classifications": diagnostic.unmatched_classifications,
        "unmatched_extractions": diagnostic.unmatched_extractions,
        "assigned_tables": [
            {
                "table_index": table.table_index,
                "table_type": table.table_type,
                "metric_values_generated": len(table.metric_values),
                "row_count": len(table.rows),
                "column_count": max((len(row) for row in table.rows), default=0),
            }
            for table in tables
        ],
    }


def _page_signals(table_text: str) -> dict[str, Any]:
    normalized_text = _normalize_text(table_text)
    compact_text = _compact(normalized_text)
    return {
        "note_context": _has_note_context(normalized_text, compact_text),
        "supporting_schedule_markers": _found_loose_markers(
            normalized_text,
            compact_text,
            SUPPORTING_SCHEDULE_MARKERS,
        ),
        "financial_highlights_markers": _found_loose_markers(
            normalized_text,
            compact_text,
            FINANCIAL_HIGHLIGHTS_MARKERS,
        ),
        "formal_income_statement_headings": _found_loose_markers(
            normalized_text,
            compact_text,
            INCOME_STATEMENT_FORMAL_HEADINGS,
        ),
        "formal_cash_flow_headings": _found_loose_markers(
            normalized_text,
            compact_text,
            CASH_FLOW_FORMAL_HEADINGS,
        ),
        "formal_balance_sheet_headings": _found_loose_markers(
            normalized_text,
            compact_text,
            BALANCE_SHEET_FORMAL_HEADINGS,
        ),
    }


def _classification_changes(page_sources: list[PageReplaySource]) -> dict[str, Any]:
    removed: Counter[str] = Counter()
    added: Counter[str] = Counter()
    pages_changed: list[dict[str, Any]] = []
    for source in page_sources:
        original_types = source.page_table_type.table_types
        decisions = _tightening_decisions(original_types, source.raw_extraction.raw_tables)
        tightened_types = _tightened_table_types(original_types, decisions)
        if original_types == tightened_types:
            continue
        for table_type in set(original_types) - set(tightened_types):
            removed[table_type] += 1
        for table_type in set(tightened_types) - set(original_types):
            added[table_type] += 1
        pages_changed.append(
            {
                "page_number": source.page_table_type.page_number,
                "original_table_types": original_types,
                "tightened_table_types": tightened_types,
                "removed": [
                    decision.table_type
                    for decision in decisions
                    if decision.action == "remove"
                ],
                "reasons": {
                    decision.table_type: list(decision.reasons)
                    for decision in decisions
                    if decision.action == "remove"
                },
            }
        )
    return {
        "pages_changed": len(pages_changed),
        "removed_by_type": dict(sorted(removed.items())),
        "added_by_type": dict(sorted(added.items())),
        "examples": pages_changed[:50],
    }


def _variant_delta(original: dict[str, Any], tightened: dict[str, Any]) -> dict[str, Any]:
    fields = (
        "total_classified_tables",
        "total_matched_tables",
        "unmatched_classified_types",
        "unclassified_tables",
        "metric_values_generated",
        "duplicate_metric_groups",
        "conflicting_metric_groups",
    )
    return {
        field: tightened[field] - original[field]
        for field in fields
    }


def _summarize_reports(report_results: list[dict[str, Any]]) -> dict[str, Any]:
    totals: dict[str, dict[str, int]] = {
        "original": defaultdict(int),
        "tightened": defaultdict(int),
        "delta": defaultdict(int),
    }
    for report in report_results:
        for variant in ("original", "tightened"):
            for field, value in report[variant].items():
                if isinstance(value, int):
                    totals[variant][field] += value
        for field, value in report["delta"].items():
            totals["delta"][field] += value
    return {
        "original": dict(totals["original"]),
        "tightened": dict(totals["tightened"]),
        "delta": dict(totals["delta"]),
    }


def _observed_root_causes(focus_traces: list[dict[str, Any]]) -> list[dict[str, Any]]:
    causes: list[dict[str, Any]] = []
    for trace in focus_traces:
        causes.append(
            {
                "report": trace["report"],
                "page_number": trace["page_number"],
                "removed_classified_types": trace["removed_classified_types"],
                "signals_responsible": {
                    decision["table_type"]: decision["matched_keywords"]
                    for decision in trace["type_decisions"]
                    if decision["table_type"] in trace["removed_classified_types"]
                },
                "tightening_reason": {
                    decision["table_type"]: decision["reasons"]
                    for decision in trace["type_decisions"]
                    if decision["table_type"] in trace["removed_classified_types"]
                },
            }
        )
    return causes


def _proposed_rules() -> dict[str, list[str]]:
    return {
        "primary_financial_statements": [
            "Only emit income_statement for formal income statement headings or full primary-statement structures.",
            "Only emit cash_flow_statement for formal cash-flow statement headings or operating/investing/financing activity blocks.",
            "Do not treat financial highlights/key-figures tables as multiple primary statements solely because they include turnover, profit, and cash-flow summary rows.",
        ],
        "note_disclosures": [
            "When the table is a numbered note or notes page, prefer notes or a specific note type unless a formal primary statement heading is present.",
            "Do not classify a cash generated from operations note as cash_flow_statement.",
            "Do not classify expense notes such as distribution costs or administrative expenses as income_statement.",
        ],
        "supporting_schedules": [
            "Classify supporting schedules with specific note/schedule labels when possible.",
            "Keep primary-statement labels only when the extracted heading explicitly names the primary statement.",
            "Use multi-label or table-splitting only for genuine multi-logical tables, not to preserve classifier false positives.",
        ],
    }


def _top_unmatched(unmatched_classifications: list[str]) -> list[dict[str, Any]]:
    counter = Counter(
        item.split(" table_type=", 1)[1] if " table_type=" in item else item
        for item in unmatched_classifications
    )
    return [
        {"table_type": table_type, "count": count}
        for table_type, count in counter.most_common(20)
    ]


def _matched_keywords(normalized_text: str, table_type: str) -> list[str]:
    keywords = _keywords_for_table_type(table_type)
    if not keywords:
        keywords = tuple(
            token
            for token in _normalize_key(table_type).split("_")
            if token and token not in {"financial", "statement", "table", "note", "notes"}
        )
    return [
        keyword
        for keyword in keywords
        if _contains_phrase(normalized_text, keyword)
        or _compact(_normalize_text(keyword)) in _compact(normalized_text)
    ]


def _page_table_text(raw_tables: list[list[list[str]]]) -> str:
    parts: list[str] = []
    for raw_table in raw_tables:
        parts.append(_table_text(raw_table))
    return "\n\n".join(part for part in parts if part.strip())


def _table_text(rows: list[list[str]]) -> str:
    lines: list[str] = []
    for row in rows:
        values = [str(cell).strip() for cell in row if str(cell).strip()]
        if values:
            lines.append(" | ".join(values))
    return "\n".join(lines)


def _has_note_context(normalized_text: str, compact_text: str) -> bool:
    return _has_any_loose(normalized_text, compact_text, NOTE_CONTEXT_MARKERS)


def _has_any_loose(
    normalized_text: str,
    compact_text: str,
    markers: Iterable[str],
) -> bool:
    return bool(_found_loose_markers(normalized_text, compact_text, markers))


def _found_loose_markers(
    normalized_text: str,
    compact_text: str,
    markers: Iterable[str],
) -> list[str]:
    found: list[str] = []
    for marker in markers:
        normalized_marker = _normalize_text(marker)
        if not normalized_marker:
            continue
        if _contains_phrase(normalized_text, marker):
            found.append(marker)
            continue
        if _compact(normalized_marker) in compact_text:
            found.append(marker)
    return found


def _compact(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", value.lower())


def _dedupe_preserve_order(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        normalized = _normalize_key(value)
        if normalized in seen:
            continue
        seen.add(normalized)
        result.append(value)
    return result


if __name__ == "__main__":
    raise SystemExit(main())
