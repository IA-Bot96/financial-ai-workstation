"""Tests for OCR V2 Bridge Phase B0-B2 extraction bridge only."""

from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path
from uuid import uuid4

BACKEND_DIR = Path(__file__).resolve().parents[2]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from ocr import (  # noqa: E402
    CandidateCaptureInput,
    ExtractedTableDocumentContext,
    LUCKY_PRODUCTION_WORKBOOK_FINGERPRINT,
    OCRV2Basis,
    OCRV2CandidateAdapter,
    OCRV2EntityScope,
    OCRV2StatementType,
    OCRV2TableAdapter,
    default_ocr_v2_bridge_config,
    write_ocr_v2_bridge_phase_report,
)


def _workspace_tmp(test_name: str) -> Path:
    path = Path("output/ocr_v2_test_artifacts") / f"{test_name}_{uuid4().hex}"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _write_csv(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _bridge_fixture_dir() -> Path:
    directory = _workspace_tmp("bridge_fixture")
    _write_csv(
        directory / "page_0164_bbox_00_bbox_camelot_stream_table_00.csv",
        "\n".join(
            [
                "PKR in '000,2024,2025",
                'Turnover,"115,324,942","124,511,744"',
                'Gross Profit,"38,804,572","42,684,684"',
                "Vertical Analysis - (%),2024,2025",
                "Turnover,100.00,100.00",
            ]
        ),
    )
    _write_csv(
        directory / "page_0322_bbox_00_bbox_camelot_stream_table_00.csv",
        "\n".join(
            [
                ",,Note,2025,2024",
                ",,,(PKR in '000'),",
                ",Revenue,,\"25,417,143\",\"26,282,162\"",
                ",Cash and cash equivalents,,\"11,410\",\"13,424\"",
            ]
        ),
    )
    return directory


def test_table_adapter_extracts_raw_numeric_cells_from_bbox_csvs() -> None:
    tables_dir = _bridge_fixture_dir()

    result = OCRV2TableAdapter().ingest_directory(tables_dir)

    assert result.tables_processed == 2
    assert result.candidate_rows_generated == 10
    first = result.cells[0]
    assert first.raw_label == "Turnover"
    assert first.raw_value == "115,324,942"
    assert first.value_year == 2024
    assert first.page_number == 164
    assert first.table_reference == "page_0164_bbox_00_bbox_camelot_stream_table_00"
    assert first.source_scale == "source_header:PKR thousands"
    assert first.source_unit == "PKR"
    assert isinstance(first.document_context, ExtractedTableDocumentContext)
    assert first.document_context.units_scale_text is not None


def test_candidate_adapter_preserves_candidate_multiplicity() -> None:
    tables_dir = _bridge_fixture_dir()

    stream = OCRV2CandidateAdapter().build_stream(tables_dir)
    groups = Counter((row.raw_label, row.value_year) for row in stream.candidate_inputs)

    assert stream.candidate_rows_generated == 10
    assert groups[("revenue", 2025)] == 3
    revenue_2025 = [
        row for row in stream.candidate_inputs if row.raw_label == "revenue" and row.value_year == 2025
    ]
    assert {row.raw_value for row in revenue_2025} == {
        "124,511,744",
        "100.00",
        "25,417,143",
    }
    assert stream.candidate_removals == 0
    assert stream.governance_invocations == 0
    assert stream.canonical_selection_attempts == 0
    first_revenue = revenue_2025[0]
    assert first_revenue.basis == OCRV2Basis.UNCONSOLIDATED.value
    assert first_revenue.statement_type in {
        OCRV2StatementType.SUPPORTING_SCHEDULE.value,
        OCRV2StatementType.ANALYSIS_TABLE.value,
        OCRV2StatementType.NOTE.value,
    }


def test_bridge_page_statement_and_entity_mappings_are_deterministic() -> None:
    config = default_ocr_v2_bridge_config()

    assert config.basis_for_page(164) == OCRV2Basis.UNCONSOLIDATED.value
    assert config.statement_type_for_page(164) == (
        OCRV2StatementType.SUPPORTING_SCHEDULE.value
    )
    assert config.statement_type_for_page(
        164,
        section_label="Vertical Analysis - (%)",
    ) == OCRV2StatementType.ANALYSIS_TABLE.value
    assert config.entity_scope_for_page(164) == OCRV2EntityScope.ISSUER.value

    assert config.basis_for_page(322) == OCRV2Basis.CONSOLIDATED.value
    assert config.statement_type_for_page(322) == OCRV2StatementType.NOTE.value
    assert config.entity_scope_for_page(322) == OCRV2EntityScope.INVESTEE.value


def test_candidate_adapter_outputs_valid_candidate_capture_inputs() -> None:
    tables_dir = _bridge_fixture_dir()

    stream = OCRV2CandidateAdapter().build_stream(tables_dir)

    assert stream.candidate_rows_generated > 0
    for row in stream.candidate_inputs:
        restored = CandidateCaptureInput.model_validate(row.model_dump(mode="python"))
        assert restored.document_fingerprint == LUCKY_PRODUCTION_WORKBOOK_FINGERPRINT
        assert restored.statement_type
        assert restored.basis
        assert restored.entity_scope
        assert restored.source_scale
        assert restored.source_unit


def test_bridge_audit_has_required_success_values_on_real_tables() -> None:
    tmp_path = _workspace_tmp("bridge_audit")
    audit_path = tmp_path / "ocr_v2_bridge_audit.json"

    audit = OCRV2CandidateAdapter().write_bridge_audit(audit_path)
    payload = json.loads(audit_path.read_text(encoding="utf-8"))

    assert payload["tables_processed"] == 27
    assert payload["candidate_rows_generated"] > 0
    assert payload["candidate_rows_missing_required_metadata"] == 0
    assert payload["multi_candidate_metric_year_groups"] > 0
    assert payload["candidate_removals"] == 0
    assert payload["governance_invocations"] == 0
    assert payload["canonical_selection_attempts"] == 0
    assert payload["integrity_violations"] == []
    assert audit.integrity_violations == ()


def test_bridge_phase_report_writes_required_artifacts() -> None:
    tmp_path = _workspace_tmp("bridge_report")
    audit_path = tmp_path / "ocr_v2_bridge_audit.json"
    report_path = tmp_path / "ocr_v2_bridge_phase_report.json"

    report = write_ocr_v2_bridge_phase_report(
        audit_path=audit_path,
        report_path=report_path,
    )
    payload = json.loads(report_path.read_text(encoding="utf-8"))

    assert audit_path.exists()
    assert payload["phase"] == "B0-B2"
    assert payload["scope"] == "extraction_bridge_only"
    assert payload["candidate_rows_generated"] > 0
    assert payload["candidate_rows_missing_required_metadata"] == 0
    assert payload["multi_candidate_metric_year_groups"] > 0
    assert payload["candidate_capture_ready"] is True
    assert payload["governance_changes_added"] is False
    assert payload["selection_changes_added"] is False
    assert payload["workbook_changes_added"] is False
    assert payload["export_changes_added"] is False
    assert payload["new_ocr_extraction_engine_added"] is False
    assert payload["llm_logic_added"] is False
    assert payload["integrity_audit_passed"] is True
    assert report.integrity_violations == ()
