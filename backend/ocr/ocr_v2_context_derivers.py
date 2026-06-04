"""OCR V2 document-context tag derivers.

These pure deterministic derivers consume document context threaded from the
raw table bridge. They do not perform OCR extraction, governance, candidate
selection, ranking, scoring, entity resolution, workbook generation, MSIL
export, or LLM behavior.
"""

from __future__ import annotations

import re

from pydantic import BaseModel, ConfigDict

from .ocr_v2_candidate_capture import UNKNOWN_CLASSIFICATION
from .ocr_v2_contracts import OCRV2Basis, OCRV2EntityScope, OCRV2StatementType
from .ocr_v2_table_adapter import ExtractedTableDocumentContext


UNKNOWN_DERIVED_TAG = UNKNOWN_CLASSIFICATION


class DerivedTagResult(BaseModel):
    """One deterministic document-context derivation result."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    value: str
    reason: str

    @property
    def is_unknown(self) -> bool:
        return self.value == UNKNOWN_DERIVED_TAG


class BasisDeriver:
    """Derive consolidated/unconsolidated basis from explicit document text."""

    def derive(self, context: ExtractedTableDocumentContext | None) -> DerivedTagResult:
        text = _context_text(context)
        if not text:
            return _unknown("basis_not_present")
        if _contains_any(
            text,
            (
                "unconsolidated",
                "standalone",
                "stand alone",
                "separate financial statement",
                "separate statement",
            ),
        ):
            return DerivedTagResult(
                value=OCRV2Basis.UNCONSOLIDATED.value,
                reason="explicit_unconsolidated_context",
            )
        if _contains_any(
            text,
            (
                "consolidated",
                "the group",
                "group's",
                "group s",
                "group share",
            ),
        ):
            return DerivedTagResult(
                value=OCRV2Basis.CONSOLIDATED.value,
                reason="explicit_consolidated_context",
            )
        return _unknown("basis_not_present")


class StatementTypeDeriver:
    """Derive OCR V2 statement/source type from explicit document context."""

    def derive(self, context: ExtractedTableDocumentContext | None) -> DerivedTagResult:
        text = _context_text(context)
        if not text:
            return _unknown("statement_type_not_present")
        if context and context.notes_to_marker:
            return DerivedTagResult(
                value=OCRV2StatementType.NOTE.value,
                reason="notes_to_financial_statements_marker",
            )
        if "notes to" in text and "financial statement" in text:
            return DerivedTagResult(
                value=OCRV2StatementType.NOTE.value,
                reason="notes_to_financial_statements_text",
            )
        if _contains_any(
            text,
            (
                "vertical analysis",
                "horizontal analysis",
                "year on year",
                "yearonyear",
                "cumulative",
            ),
        ):
            return DerivedTagResult(
                value=OCRV2StatementType.ANALYSIS_TABLE.value,
                reason="explicit_analysis_context",
            )
        if _contains_any(
            text,
            (
                "six year",
                "six-year",
                "five year",
                "five-year",
                "financial highlights",
                "at a glance",
                "summary table",
            ),
        ):
            return DerivedTagResult(
                value=OCRV2StatementType.SUMMARY_TABLE.value,
                reason="explicit_summary_context",
            )
        if _contains_any(
            text,
            (
                "schedule of",
                "supporting schedule",
            ),
        ):
            return DerivedTagResult(
                value=OCRV2StatementType.SUPPORTING_SCHEDULE.value,
                reason="explicit_supporting_schedule_context",
            )
        if _primary_statement_title_present(text):
            return DerivedTagResult(
                value=OCRV2StatementType.PRIMARY_STATEMENT.value,
                reason="explicit_primary_statement_title",
            )
        return _unknown("statement_type_not_present")


class EntityScopeDeriver:
    """Derive high-level entity scope from explicit issuer/investee context."""

    def derive(self, context: ExtractedTableDocumentContext | None) -> DerivedTagResult:
        text = _context_text(context)
        if not text:
            return _unknown("entity_scope_not_present")
        if _contains_any(
            text,
            (
                "investment in subsidiary",
                "investment in subsidiaries",
                "investment in controlled entity",
            ),
        ):
            return DerivedTagResult(
                value=OCRV2EntityScope.SUBSIDIARY.value,
                reason="explicit_subsidiary_context",
            )
        if _contains_any(
            text,
            (
                "investment in associates",
                "investment in associate",
                "investment in joint venture",
                "investment in joint ventures",
                "net assets of associates",
                "net assets of associate",
            ),
        ):
            return DerivedTagResult(
                value=OCRV2EntityScope.INVESTEE.value,
                reason="explicit_investee_context",
            )
        if _contains_any(text, ("statement of", "issuer", "company's", "company s")):
            return DerivedTagResult(
                value=OCRV2EntityScope.ISSUER.value,
                reason="explicit_issuer_context",
            )
        return _unknown("entity_scope_not_present")


def _context_text(context: ExtractedTableDocumentContext | None) -> str:
    if context is None:
        return ""
    values = [
        context.statement_title,
        context.section_heading,
        "notes to financial statements" if context.notes_to_marker else None,
        " ".join(context.named_entities),
        context.units_scale_text,
    ]
    return _normalize_text(" ".join(value for value in values if value))


def _normalize_text(value: str) -> str:
    text = value.replace("\u2018", "'").replace("\u2019", "'")
    text = text.replace("\u2013", "-").replace("\u2014", "-")
    text = text.lower()
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def _contains_any(text: str, markers: tuple[str, ...]) -> bool:
    compact = text.replace(" ", "")
    return any(marker in text or marker.replace(" ", "") in compact for marker in markers)


def _primary_statement_title_present(text: str) -> bool:
    if "analysis of statement" in text:
        return False
    return _contains_any(
        text,
        (
            "statement of financial position",
            "statement of profit or loss",
            "statement of comprehensive income",
            "statement of cash flow",
            "statement of cash flows",
            "statement of changes in equity",
        ),
    )


def _unknown(reason: str) -> DerivedTagResult:
    return DerivedTagResult(value=UNKNOWN_DERIVED_TAG, reason=reason)


__all__ = [
    "UNKNOWN_DERIVED_TAG",
    "BasisDeriver",
    "DerivedTagResult",
    "EntityScopeDeriver",
    "StatementTypeDeriver",
]
