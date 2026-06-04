"""Tests for OCR V2 G1.0b page-level context enrichment."""

from __future__ import annotations

import sys
from pathlib import Path
from uuid import uuid4

BACKEND_DIR = Path(__file__).resolve().parents[2]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from ocr import OCRV2PageContextProvider, OCRV2TableAdapter  # noqa: E402


def _workspace_tmp(test_name: str) -> Path:
    path = Path("output/ocr_v2_test_artifacts") / f"{test_name}_{uuid4().hex}"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _write_csv(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def test_page_level_statement_title_is_threaded_to_cells() -> None:
    tables_dir = _workspace_tmp("g10b_statement_title")
    _write_csv(
        tables_dir / "page_0240_bbox_00_bbox_camelot_stream_table_00.csv",
        "\n".join(
            [
                ",Note,2025,2024",
                ",,(PKR in '000'),",
                'Total assets,,"266,748,030","234,018,090"',
            ]
        ),
    )
    provider = OCRV2PageContextProvider(
        page_text_by_page={
            240: "\n".join(
                [
                    "Unconsolidated Statement of",
                    "Financial Position",
                    "as at June 30, 2025",
                ]
            )
        }
    )

    cells = OCRV2TableAdapter(page_context_provider=provider).ingest_directory(tables_dir).cells

    assert len(cells) == 2
    assert all(
        cell.document_context.statement_title
        == "Unconsolidated Statement of Financial Position"
        for cell in cells
    )


def test_notes_marker_is_threaded_from_page_text() -> None:
    tables_dir = _workspace_tmp("g10b_notes_marker")
    _write_csv(
        tables_dir / "page_0322_bbox_00_bbox_camelot_stream_table_00.csv",
        "\n".join(
            [
                "Note,2025,2024",
                "(PKR in '000'),,",
                'Revenue,"27,828,317","27,017,286"',
            ]
        ),
    )
    provider = OCRV2PageContextProvider(
        page_text_by_page={
            322: "\n".join(
                [
                    "Notes to the Consolidated",
                    "Financial Statements",
                    "For the year ended June 30, 2025",
                ]
            )
        }
    )

    cells = OCRV2TableAdapter(page_context_provider=provider).ingest_directory(tables_dir).cells

    assert cells
    assert all(cell.document_context.notes_to_marker for cell in cells)
    assert all(
        cell.document_context.statement_title
        == "Notes to the Consolidated Financial Statements"
        for cell in cells
    )


def test_entity_context_is_threaded_without_page_ranges() -> None:
    tables_dir = _workspace_tmp("g10b_entity_context")
    _write_csv(
        tables_dir / "page_0321_bbox_00_bbox_camelot_stream_table_00.csv",
        "\n".join(
            [
                "Note,2025,2024",
                "(PKR in '000'),,",
                'Investment at cost,"6,870,050","6,870,050"',
            ]
        ),
    )
    provider = OCRV2PageContextProvider(
        page_text_by_page={
            321: "\n".join(
                [
                    "8. INVESTMENT IN ASSOCIATES",
                    "8.2 Lucky Rawji Holdings Limited (LRHL)",
                    "Investment at cost 6,870,050 6,870,050",
                ]
            )
        }
    )

    cells = OCRV2TableAdapter(page_context_provider=provider).ingest_directory(tables_dir).cells

    assert cells
    assert all(cell.document_context.entity_context for cell in cells)
    assert "INVESTMENT IN ASSOCIATES" in cells[0].document_context.entity_context
