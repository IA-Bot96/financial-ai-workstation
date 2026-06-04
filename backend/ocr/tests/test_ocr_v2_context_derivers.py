"""Tests for OCR V2 G1 document-context derivers."""

from __future__ import annotations

import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[2]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from ocr import (  # noqa: E402
    UNKNOWN_DERIVED_TAG,
    BasisDeriver,
    EntityScopeDeriver,
    ExtractedTableCell,
    ExtractedTableDocumentContext,
    OCRV2Basis,
    OCRV2CandidateAdapter,
    OCRV2EntityScope,
    OCRV2StatementType,
    StatementTypeDeriver,
)


def _cell(
    *,
    page_number: int,
    context: ExtractedTableDocumentContext,
    section_label: str | None = None,
) -> ExtractedTableCell:
    return ExtractedTableCell(
        raw_value="1,234",
        raw_label="Turnover",
        value_year=2025,
        page_number=page_number,
        table_reference=f"page_{page_number:04d}_bbox_00_fixture.csv",
        locator=f"page_{page_number:04d}:row:1:col:2",
        source_scale="source_header:PKR thousands",
        source_unit="PKR",
        section_label=section_label,
        source_file=f"page_{page_number:04d}.csv",
        document_context=context,
    )


def test_basis_deriver_uses_explicit_statement_context() -> None:
    deriver = BasisDeriver()

    unconsolidated = deriver.derive(
        ExtractedTableDocumentContext(
            statement_title="Unconsolidated Statement of Financial Position"
        )
    )
    consolidated = deriver.derive(
        ExtractedTableDocumentContext(
            statement_title="Consolidated Statement of Cash Flows"
        )
    )
    unknown = deriver.derive(
        ExtractedTableDocumentContext(statement_title="Financial Position")
    )

    assert unconsolidated.value == OCRV2Basis.UNCONSOLIDATED.value
    assert consolidated.value == OCRV2Basis.CONSOLIDATED.value
    assert unknown.value == UNKNOWN_DERIVED_TAG


def test_statement_type_deriver_keeps_analysis_and_supporting_distinct() -> None:
    deriver = StatementTypeDeriver()

    primary = deriver.derive(
        ExtractedTableDocumentContext(
            statement_title="Unconsolidated Statement of Profit or Loss"
        )
    )
    note = deriver.derive(
        ExtractedTableDocumentContext(notes_to_marker=True)
    )
    supporting = deriver.derive(
        ExtractedTableDocumentContext(
            statement_title="Supporting Schedule of Financial Position"
        )
    )
    analysis = deriver.derive(
        ExtractedTableDocumentContext(
            statement_title="Analysis of Statement of Financial Position",
            section_heading="Vertical Analysis - (%)",
        )
    )
    summary = deriver.derive(
        ExtractedTableDocumentContext(statement_title="Six Year Summary")
    )

    assert primary.value == OCRV2StatementType.PRIMARY_STATEMENT.value
    assert note.value == OCRV2StatementType.NOTE.value
    assert supporting.value == OCRV2StatementType.SUPPORTING_SCHEDULE.value
    assert analysis.value == OCRV2StatementType.ANALYSIS_TABLE.value
    assert summary.value == OCRV2StatementType.SUMMARY_TABLE.value


def test_entity_scope_deriver_uses_explicit_entity_context() -> None:
    deriver = EntityScopeDeriver()

    issuer = deriver.derive(
        ExtractedTableDocumentContext(
            statement_title="Unconsolidated Statement of Financial Position"
        )
    )
    investee = deriver.derive(
        ExtractedTableDocumentContext(
            section_heading="Investment in associates",
            named_entities=("ASIL",),
        )
    )
    subsidiary = deriver.derive(
        ExtractedTableDocumentContext(section_heading="Investment in subsidiaries")
    )
    unknown = deriver.derive(
        ExtractedTableDocumentContext(section_heading="Property and equipment")
    )

    assert issuer.value == OCRV2EntityScope.ISSUER.value
    assert investee.value == OCRV2EntityScope.INVESTEE.value
    assert subsidiary.value == OCRV2EntityScope.SUBSIDIARY.value
    assert unknown.value == UNKNOWN_DERIVED_TAG


def test_candidate_adapter_prefers_derived_tags_when_explicit() -> None:
    cell = _cell(
        page_number=999,
        context=ExtractedTableDocumentContext(
            statement_title="Unconsolidated Statement of Financial Position"
        ),
    )

    row = OCRV2CandidateAdapter().adapt_cells((cell,))[0]

    assert row.raw_label == "revenue"
    assert row.basis == OCRV2Basis.UNCONSOLIDATED.value
    assert row.statement_type == OCRV2StatementType.PRIMARY_STATEMENT.value
    assert row.entity_scope == OCRV2EntityScope.ISSUER.value


def test_candidate_adapter_falls_back_to_page_ranges_when_unknown() -> None:
    cell = _cell(
        page_number=240,
        context=ExtractedTableDocumentContext(section_heading="ASSETS"),
    )

    row = OCRV2CandidateAdapter().adapt_cells((cell,))[0]

    assert row.basis == OCRV2Basis.UNCONSOLIDATED.value
    assert row.statement_type == OCRV2StatementType.PRIMARY_STATEMENT.value
    assert row.entity_scope == OCRV2EntityScope.ISSUER.value
