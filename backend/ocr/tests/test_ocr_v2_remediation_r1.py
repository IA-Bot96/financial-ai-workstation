"""Tests for OCR V2 remediation sprint R1."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from uuid import uuid4

BACKEND_DIR = Path(__file__).resolve().parents[2]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from ocr import (  # noqa: E402
    OCRV2CandidateAdapter,
    OCRV2StatementType,
    OCRV2TableAdapter,
    default_ocr_v2_bridge_config,
    prepare_candidates_for_canonical_selection,
    write_ocr_v2_remediation_r1_artifacts,
)


def _workspace_tmp(test_name: str) -> Path:
    path = Path("output/ocr_v2_test_artifacts") / f"{test_name}_{uuid4().hex}"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _write_csv(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def test_r1_aliases_resolve_missing_census_metrics_and_source_guards() -> None:
    config = default_ocr_v2_bridge_config()

    assert config.canonical_metric_for_label("Turnover") == "revenue"
    assert config.canonical_metric_for_label("Net Revenue") == "revenue"
    assert config.canonical_metric_for_label("Gross profit") == "gross_profit"
    assert config.canonical_metric_for_label("TOTAL ASSETS") == "total_assets"
    assert config.canonical_metric_for_label("Earnings per share") == "eps"
    assert config.canonical_metric_for_label("Basic earnings per share") == "eps"
    assert config.canonical_metric_for_label("Earning per sha re (Rupees)") == "eps"
    assert config.canonical_metric_for_label("Long-term financing") == "long_term_debt"
    assert config.canonical_metric_for_cell(
        "Long term finance",
        page_number=162,
        value_year=2020,
    ) == "long_term_debt_summary_reference"
    assert config.canonical_metric_for_cell(
        "Net Cash from Operating Activities",
        page_number=162,
        value_year=2023,
    ) == "operating_cash_flow"
    assert config.canonical_metric_for_cell(
        "Net Cash from Operating Activities",
        page_number=162,
        value_year=2025,
    ) == "operating_cash_flow_summary_reference"


def test_r1_table_adapter_preserves_active_million_scale_after_eps_row() -> None:
    tables_dir = _workspace_tmp("r1_scale_fixture")
    _write_csv(
        tables_dir / "page_0162_bbox_00_bbox_camelot_stream_table_00.csv",
        "\n".join(
            [
                "Financial Position (PKR in million),2024,2025",
                "Turnover - Net,\"115,325\",\"124,512\"",
                "Earning per share (Rupees),18.91,22.59",
                "Net Cash from Operating Activities,\"27,581\",\"27,573\"",
            ]
        ),
    )

    cells = OCRV2TableAdapter().ingest_directory(tables_dir).cells
    eps = [cell for cell in cells if cell.raw_label == "Earning per share (Rupees)"]
    ocf = [cell for cell in cells if cell.raw_label == "Net Cash from Operating Activities"]

    assert {cell.source_scale for cell in eps} == {"source_header:full"}
    assert {cell.source_unit for cell in eps} == {"PKR_per_share"}
    assert {cell.source_scale for cell in ocf} == {"source_header:PKR millions"}
    assert {cell.source_unit for cell in ocf} == {"PKR"}


def test_r1_duplicate_pdfplumber_value_rows_are_retained_as_losing_evidence() -> None:
    tables_dir = _workspace_tmp("r1_duplicate_fixture")
    _write_csv(
        tables_dir / "page_0164_bbox_00_bbox_camelot_stream_table_00.csv",
        "\n".join(
            [
                "PKR in '000,2024,2025",
                'Turnover,"115,324,942","124,511,744"',
            ]
        ),
    )
    _write_csv(
        tables_dir / "page_0164_bbox_00_bbox_pdfplumber_text_table_00.csv",
        "\n".join(
            [
                "PKR in '000,2024,2025",
                'Turnover,"115,324,942","124,511,744"',
            ]
        ),
    )

    stream = OCRV2CandidateAdapter().build_stream(tables_dir)
    revenue_rows = [
        row for row in stream.candidate_inputs if row.raw_label == "revenue"
    ]

    assert len(revenue_rows) == 4
    assert {row.statement_type for row in revenue_rows} == {
        OCRV2StatementType.SUPPORTING_SCHEDULE.value,
        OCRV2StatementType.ANALYSIS_TABLE.value,
    }
    assert stream.candidate_removals == 0
    assert stream.canonical_selection_attempts == 0
    assert stream.governance_invocations == 0


def test_r1_preselection_collapses_exact_duplicates_before_selection() -> None:
    from ocr import CandidateCapture, EntityGovernance, ScaleGovernance, StatementGovernance

    rows = [
        {
            "raw_value": "41,870,796",
            "raw_label": "revenue",
            "value_year": 2020,
            "page_number": 164,
            "table_reference": "page_0164_bbox_00_bbox_camelot_stream_table_00",
            "document_fingerprint": "fixture",
            "locator": "camelot:row:2:col:2",
            "statement_type": OCRV2StatementType.SUPPORTING_SCHEDULE.value,
            "basis": "unconsolidated",
            "entity_scope": "ISSUER",
            "source_scale": "source_header:PKR thousands",
            "source_unit": "PKR",
        },
        {
            "raw_value": "41,870,796",
            "raw_label": "revenue",
            "value_year": 2020,
            "page_number": 164,
            "table_reference": "page_0164_bbox_00_bbox_pdfplumber_text_table_00",
            "document_fingerprint": "fixture",
            "locator": "pdfplumber:row:3:col:4",
            "statement_type": OCRV2StatementType.ANALYSIS_TABLE.value,
            "basis": "unconsolidated",
            "entity_scope": "ISSUER",
            "source_scale": "source_header:PKR thousands",
            "source_unit": "PKR",
        },
    ]
    candidates = CandidateCapture().capture(rows).candidates
    statement_governed = StatementGovernance().govern(candidates).governed_candidates
    scale_governed = ScaleGovernance().govern(statement_governed).governed_candidates
    entity_governed = EntityGovernance().govern(scale_governed).entity_governed_candidates

    result = prepare_candidates_for_canonical_selection(entity_governed)

    assert result.duplicates_detected == 2
    assert result.duplicates_collapsed == 1
    assert result.provenance_preserved is True
    assert result.output_candidates == 1
    assert result.duplicate_groups[0].duplicate_count == 2


def test_r1_artifact_writer_generates_expected_66_cell_audit() -> None:
    tmp_path = _workspace_tmp("r1_artifacts")
    workbook_path = tmp_path / "ocr_v2_lucky_workbook_r1.xlsx"
    metric_resolution_path = tmp_path / "metric_resolution_audit.json"
    analysis_path = tmp_path / "analysis_table_classification_audit.json"
    dedup_path = tmp_path / "candidate_dedup_audit.json"
    eps_path = tmp_path / "eps_alias_audit.json"
    source_precedence_path = tmp_path / "source_precedence_audit.json"
    source_insufficient_path = tmp_path / "source_insufficient_audit.json"
    scale_capture_path = tmp_path / "scale_capture_audit.json"
    r1_audit_path = tmp_path / "ocr_v2_r1_audit.json"
    run_audit_path = tmp_path / "ocr_v2_r1_run_audit.json"
    report_path = tmp_path / "ocr_v2_r1_report.json"
    candidates_path = tmp_path / "ocr_v2_lucky_candidates_r1.json"
    registry_path = tmp_path / "ocr_v2_lucky_registry_r1.json"

    write_ocr_v2_remediation_r1_artifacts(
        workbook_path=workbook_path,
        candidates_path=candidates_path,
        registry_path=registry_path,
        analysis_table_classification_audit_path=analysis_path,
        candidate_dedup_audit_path=dedup_path,
        eps_alias_audit_path=eps_path,
        metric_resolution_audit_path=metric_resolution_path,
        source_precedence_audit_path=source_precedence_path,
        source_insufficient_audit_path=source_insufficient_path,
        scale_capture_audit_path=scale_capture_path,
        r1_audit_path=r1_audit_path,
        run_audit_path=run_audit_path,
        report_path=report_path,
    )
    r1_payload = json.loads(r1_audit_path.read_text(encoding="utf-8"))
    metric_payload = json.loads(metric_resolution_path.read_text(encoding="utf-8"))
    analysis_payload = json.loads(analysis_path.read_text(encoding="utf-8"))
    dedup_payload = json.loads(dedup_path.read_text(encoding="utf-8"))
    eps_payload = json.loads(eps_path.read_text(encoding="utf-8"))
    source_payload = json.loads(source_precedence_path.read_text(encoding="utf-8"))
    scale_payload = json.loads(scale_capture_path.read_text(encoding="utf-8"))
    report_payload = json.loads(report_path.read_text(encoding="utf-8"))

    assert workbook_path.exists()
    assert candidates_path.exists()
    assert registry_path.exists()
    assert r1_payload["truth_set_cells"] == 66
    assert r1_payload["coverage"]["exact_matches"] == 46
    assert r1_payload["coverage"]["missing_cells"] == 6
    assert r1_payload["coverage"]["value_mismatches"] == 0
    assert r1_payload["coverage"]["scale_mismatches"] == 0
    assert r1_payload["coverage"]["source_insufficient_correct_abstentions"] == 14
    assert r1_payload["success_criteria"]["revenue_coverage_restored"] is True
    assert r1_payload["success_criteria"]["gross_profit_coverage_restored"] is True
    assert r1_payload["success_criteria"]["total_assets_coverage_restored"] is True
    assert r1_payload["success_criteria"]["eps_coverage_restored"] is True
    assert metric_payload["coverage_restored"] == {
        "eps": True,
        "gross_profit": True,
        "revenue": True,
        "total_assets": True,
    }
    assert analysis_payload["analysis_like_rows_misclassified"] == 0
    assert dedup_payload["duplicates_detected"] > 0
    assert dedup_payload["duplicates_collapsed"] > 0
    assert dedup_payload["provenance_preserved"] is True
    assert eps_payload["legacy_eps_metric_candidates_remaining"] == 0
    assert eps_payload["eps_candidates_resolved"] > 0
    assert source_payload["source_precedence_issue_corrected"] is True
    assert source_payload["conflicts_resolved"] == source_payload["precedence_conflicts"]
    assert scale_payload["operating_cash_flow_millions_captured"] is True
    assert report_payload["coverage_improves_beyond_previous_audit"] is True
    assert report_payload["candidate_ambiguity"]["materially_reduced"] is True
