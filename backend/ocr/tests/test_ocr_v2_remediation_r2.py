"""Tests for OCR V2 remediation sprint R2."""

from __future__ import annotations

import sys
from pathlib import Path
from uuid import uuid4

BACKEND_DIR = Path(__file__).resolve().parents[2]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from ocr import OCRV2CandidateAdapter, OCRV2TableAdapter, default_ocr_v2_bridge_config  # noqa: E402


def _workspace_tmp(test_name: str) -> Path:
    path = Path("output/ocr_v2_test_artifacts") / f"{test_name}_{uuid4().hex}"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _write_csv(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def test_r2_ocf_label_disambiguation_preserves_net_operating_cash_flow() -> None:
    config = default_ocr_v2_bridge_config()

    assert (
        config.canonical_metric_for_label("Net cash generated from operating activities")
        == "operating_cash_flow"
    )
    assert (
        config.canonical_metric_for_label("Cash generated from operations")
        == "cash_generated_from_operations"
    )


def test_r2_unlabeled_liabilities_subtotal_is_captured_from_extracted_row() -> None:
    tables_dir = _workspace_tmp("r2_liabilities_subtotal")
    _write_csv(
        tables_dir / "page_0240_bbox_00_bbox_camelot_stream_table_00.csv",
        "\n".join(
            [
                ",Note,2025,2024",
                ",,(PKR in '000'),",
                "CURRENT LIABILITIES,,,",
                'Trade and other payables,24,"27,300,919","30,006,625"',
                ',,"58,641,383","54,188,473"',
                ',,"90,837,630","86,256,813"',
                'TOTAL EQUITY AND LIABILITIES,,"266,748,030","234,018,090"',
            ]
        ),
    )

    cells = OCRV2TableAdapter().ingest_directory(tables_dir).cells
    subtotal_cells = [cell for cell in cells if cell.raw_label == "total_liabilities"]

    assert len(subtotal_cells) == 2
    assert {cell.raw_value for cell in subtotal_cells} == {
        "90,837,630",
        "86,256,813",
    }
    assert {cell.value_year for cell in subtotal_cells} == {2024, 2025}
    assert all("row:6" in cell.locator for cell in subtotal_cells)
    assert all(cell.section_label == "CURRENT LIABILITIES" for cell in subtotal_cells)


def test_r2_bridge_emits_distinct_ocf_candidates_and_total_liabilities() -> None:
    tables_dir = _workspace_tmp("r2_bridge_stream")
    _write_csv(
        tables_dir / "page_0243_bbox_00_bbox_camelot_stream_table_00.csv",
        "\n".join(
            [
                ",Note,2025,2024",
                ",,(PKR in '000'),",
                "CASH FLOWS FROM OPERATING ACTIVITIES,,,",
                'Cash generated from operations,36,"33,808,781","30,937,432"',
                'Net cash generated from operating activities,,"27,572,567","27,580,741"',
            ]
        ),
    )
    _write_csv(
        tables_dir / "page_0240_bbox_00_bbox_camelot_stream_table_00.csv",
        "\n".join(
            [
                ",Note,2025,2024",
                ",,(PKR in '000'),",
                "CURRENT LIABILITIES,,,",
                'Trade and other payables,24,"27,300,919","30,006,625"',
                ',,"58,641,383","54,188,473"',
                ',,"90,837,630","86,256,813"',
                'TOTAL EQUITY AND LIABILITIES,,"266,748,030","234,018,090"',
            ]
        ),
    )

    stream = OCRV2CandidateAdapter().build_stream(tables_dir)
    grouped = {(row.raw_label, row.value_year): row for row in stream.candidate_inputs}

    assert ("cash_generated_from_operations", 2025) in grouped
    assert ("cash_generated_from_operations", 2024) in grouped
    assert grouped[("operating_cash_flow", 2025)].raw_value == "27,572,567"
    assert grouped[("operating_cash_flow", 2024)].raw_value == "27,580,741"
    assert grouped[("total_liabilities", 2025)].raw_value == "90,837,630"
    assert grouped[("total_liabilities", 2024)].raw_value == "86,256,813"
    assert stream.candidate_removals == 0
    assert stream.governance_invocations == 0
    assert stream.canonical_selection_attempts == 0
