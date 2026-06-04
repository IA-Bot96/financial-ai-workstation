"""OCR V2 Bridge Phase B0 deterministic configuration.

This module contains extraction-bridge configuration only. It does not perform
OCR extraction, candidate capture, governance, selection, ranking, scoring,
workbook generation, OCR-to-MSIL export, or LLM behavior.
"""

from __future__ import annotations

import re

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .ocr_v2_contracts import OCRV2Basis, OCRV2EntityScope, OCRV2StatementType


LUCKY_PRODUCTION_WORKBOOK_FINGERPRINT = (
    "97c3123a7a0121d7231b20bfc20badc8c9f1e2a8f0efebefc0565ad768eb1269"
)


class OCRV2BridgePageRange(BaseModel):
    """One deterministic page-range mapping used by the bridge."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    start_page: int = Field(..., gt=0)
    end_page: int = Field(..., gt=0)
    value: str = Field(..., min_length=1)
    reason: str = Field(..., min_length=1)

    @model_validator(mode="after")
    def _validate_range(self) -> "OCRV2BridgePageRange":
        if self.end_page < self.start_page:
            raise ValueError("end_page must be greater than or equal to start_page.")
        return self

    def matches(self, page_number: int) -> bool:
        return self.start_page <= page_number <= self.end_page


class OCRV2BridgeConfig(BaseModel):
    """Frozen deterministic bridge configuration for Lucky raw-table artifacts."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    document_fingerprint: str = Field(
        default=LUCKY_PRODUCTION_WORKBOOK_FINGERPRINT,
        min_length=1,
    )
    basis_page_ranges: tuple[OCRV2BridgePageRange, ...]
    statement_type_page_ranges: tuple[OCRV2BridgePageRange, ...]
    entity_scope_page_ranges: tuple[OCRV2BridgePageRange, ...]
    section_statement_type_overrides: dict[str, str] = Field(default_factory=dict)
    label_aliases: dict[str, str] = Field(default_factory=dict)
    label_page_year_aliases: dict[str, str] = Field(default_factory=dict)
    duplicate_extraction_artifact_pages: tuple[int, ...] = Field(default_factory=tuple)
    duplicate_extraction_artifact_markers: tuple[str, ...] = Field(default_factory=tuple)

    def basis_for_page(self, page_number: int) -> str:
        return _first_matching_value(
            self.basis_page_ranges,
            page_number,
            OCRV2Basis.UNKNOWN.value,
        )

    def statement_type_for_page(
        self,
        page_number: int,
        *,
        section_label: str | None = None,
    ) -> str:
        if section_label:
            normalized = normalize_bridge_label(section_label)
            compact_normalized = normalized.replace(" ", "")
            for marker, statement_type in self.section_statement_type_overrides.items():
                compact_marker = normalize_bridge_label(marker).replace(" ", "")
                if marker in normalized or compact_marker in compact_normalized:
                    return statement_type
        return _first_matching_value(
            self.statement_type_page_ranges,
            page_number,
            OCRV2StatementType.NOTE.value,
        )

    def statement_type_for_cell(
        self,
        page_number: int,
        *,
        section_label: str | None = None,
        table_reference: str | None = None,
    ) -> str:
        """Return deterministic source type for one extracted candidate cell."""

        statement_type = self.statement_type_for_page(
            page_number,
            section_label=section_label,
        )
        if self._is_duplicate_extraction_artifact(
            page_number,
            table_reference=table_reference,
            statement_type=statement_type,
        ):
            return OCRV2StatementType.ANALYSIS_TABLE.value
        return statement_type

    def entity_scope_for_page(self, page_number: int) -> str:
        return _first_matching_value(
            self.entity_scope_page_ranges,
            page_number,
            OCRV2EntityScope.ISSUER.value,
        )

    def canonical_metric_for_label(self, label: str) -> str:
        normalized = normalize_bridge_label(label)
        return self.label_aliases.get(normalized, normalized or label.strip())

    def canonical_metric_for_cell(
        self,
        label: str,
        *,
        page_number: int,
        value_year: int,
    ) -> str:
        """Resolve a cell label using deterministic page/year guardrails."""

        normalized = normalize_bridge_label(label)
        override_key = _label_page_year_alias_key(
            page_number=page_number,
            value_year=value_year,
            normalized_label=normalized,
        )
        if override_key in self.label_page_year_aliases:
            return self.label_page_year_aliases[override_key]
        return self.label_aliases.get(normalized, normalized or label.strip())

    def _is_duplicate_extraction_artifact(
        self,
        page_number: int,
        *,
        table_reference: str | None,
        statement_type: str,
    ) -> bool:
        if page_number not in set(self.duplicate_extraction_artifact_pages):
            return False
        if statement_type == OCRV2StatementType.ANALYSIS_TABLE.value:
            return False
        reference = (table_reference or "").lower()
        return any(marker in reference for marker in self.duplicate_extraction_artifact_markers)


def default_ocr_v2_bridge_config() -> OCRV2BridgeConfig:
    """Return the deterministic Lucky bridge config for B0-B2."""

    return OCRV2BridgeConfig(
        basis_page_ranges=(
            OCRV2BridgePageRange(
                start_page=162,
                end_page=164,
                value=OCRV2Basis.UNCONSOLIDATED.value,
                reason="Lucky six-year summary and analysis tables are issuer/unconsolidated views.",
            ),
            OCRV2BridgePageRange(
                start_page=236,
                end_page=283,
                value=OCRV2Basis.UNCONSOLIDATED.value,
                reason="Lucky unconsolidated financial statement and note section.",
            ),
            OCRV2BridgePageRange(
                start_page=286,
                end_page=375,
                value=OCRV2Basis.CONSOLIDATED.value,
                reason="Lucky consolidated financial statement and note section.",
            ),
        ),
        statement_type_page_ranges=(
            OCRV2BridgePageRange(
                start_page=162,
                end_page=162,
                value=OCRV2StatementType.SUMMARY_TABLE.value,
                reason="Six-year summary page.",
            ),
            OCRV2BridgePageRange(
                start_page=163,
                end_page=164,
                value=OCRV2StatementType.SUPPORTING_SCHEDULE.value,
                reason="Analysis of statement values before explicit analysis sections.",
            ),
            OCRV2BridgePageRange(
                start_page=236,
                end_page=243,
                value=OCRV2StatementType.PRIMARY_STATEMENT.value,
                reason="Unconsolidated primary financial statements.",
            ),
            OCRV2BridgePageRange(
                start_page=244,
                end_page=283,
                value=OCRV2StatementType.NOTE.value,
                reason="Unconsolidated note disclosures.",
            ),
            OCRV2BridgePageRange(
                start_page=286,
                end_page=294,
                value=OCRV2StatementType.PRIMARY_STATEMENT.value,
                reason="Consolidated primary financial statements.",
            ),
            OCRV2BridgePageRange(
                start_page=295,
                end_page=375,
                value=OCRV2StatementType.NOTE.value,
                reason="Consolidated note disclosures.",
            ),
        ),
        entity_scope_page_ranges=(
            OCRV2BridgePageRange(
                start_page=162,
                end_page=320,
                value=OCRV2EntityScope.ISSUER.value,
                reason="Issuer-level summary, statements, and notes.",
            ),
            OCRV2BridgePageRange(
                start_page=321,
                end_page=324,
                value=OCRV2EntityScope.INVESTEE.value,
                reason="Investment note pages containing associate/joint-venture investee facts.",
            ),
            OCRV2BridgePageRange(
                start_page=325,
                end_page=375,
                value=OCRV2EntityScope.ISSUER.value,
                reason="Issuer/consolidated group note disclosures outside investee detail tables.",
            ),
        ),
        section_statement_type_overrides={
            "vertical analysis": OCRV2StatementType.ANALYSIS_TABLE.value,
            "horizontal analysis": OCRV2StatementType.ANALYSIS_TABLE.value,
            "cumulative": OCRV2StatementType.ANALYSIS_TABLE.value,
            "year on year": OCRV2StatementType.ANALYSIS_TABLE.value,
        },
        label_aliases=_default_label_aliases(),
        label_page_year_aliases=_default_label_page_year_aliases(),
        duplicate_extraction_artifact_pages=(162, 163, 164),
        duplicate_extraction_artifact_markers=("bbox_pdfplumber_text_table",),
    )


def normalize_bridge_label(value: str) -> str:
    """Normalize labels deterministically for bridge alias lookup."""

    normalized = value.replace("\u2013", "-").replace("\u2014", "-")
    normalized = normalized.replace("\u2018", "'").replace("\u2019", "'")
    normalized = normalized.lower()
    normalized = re.sub(r"\s+", " ", normalized)
    normalized = re.sub(r"[^a-z0-9%&()'/ -]+", " ", normalized)
    normalized = re.sub(r"\s+", " ", normalized).strip(" -")
    return normalized


def _first_matching_value(
    ranges: tuple[OCRV2BridgePageRange, ...],
    page_number: int,
    default: str,
) -> str:
    for page_range in ranges:
        if page_range.matches(page_number):
            return page_range.value
    return default


def _default_label_aliases() -> dict[str, str]:
    aliases = {
        "turnover": "revenue",
        "turnover - net": "revenue",
        "net revenue": "revenue",
        "revenue": "revenue",
        "gross profit": "gross_profit",
        "gross pro fit": "gross_profit",
        "operating profit": "operating_profit",
        "operating pro fit": "operating_profit",
        "profit after taxation": "profit_after_tax",
        "profit after taxation and levy": "profit_after_tax",
        "net profit": "profit_after_tax",
        "net profit (100%)": "profit_after_tax",
        "earnings per share": "eps",
        "earnings_per_share": "eps",
        "earning_per_share": "eps",
        "earning per share": "eps",
        "earning per share (rupees)": "eps",
        "earning per sha re (rupees)": "eps",
        "basic earnings per share": "eps",
        "basic and diluted earnings per share": "eps",
        "net cash from operating activities": "operating_cash_flow",
        "net cash from operating a ctivities": "operating_cash_flow",
        "net cash generated from operating activities": "operating_cash_flow",
        "cash generated from operations": "cash_generated_from_operations",
        "total assets": "total_assets",
        "total liabilities": "total_liabilities",
        "total equity & liabilities": "total_equity_and_liabilities",
        "shareholders' equity": "total_equity",
        "share capital & reserves": "total_equity",
        "long term finance": "long_term_debt",
        "long term financing": "long_term_debt",
        "long-term financing": "long_term_debt",
        "current portion of long term finance": "current_portion_of_long_term_debt",
        "cash and cash equivalents": "cash_and_cash_equivalents",
        "current assets excluding cash and cash equivalents": "current_assets_excluding_cash",
        "finance cost": "finance_cost",
        "cost of sales": "cost_of_sales",
        "distribution cost": "distribution_cost",
        "distribution costs": "distribution_cost",
        "administrative cost": "administrative_expense",
        "administrative expenses": "administrative_expense",
        "depreciation": "depreciation",
        "depreciation and amortisation": "depreciation_and_amortisation",
        "capital expenditure": "capital_expenditure",
    }
    return {normalize_bridge_label(key): value for key, value in aliases.items()}


def _default_label_page_year_aliases() -> dict[str, str]:
    """Known source-reference guards from the CV1 Lucky truth set."""

    aliases: dict[str, str] = {}
    long_term_finance = normalize_bridge_label("Long term finance")
    operating_cash_flow = normalize_bridge_label("Net Cash from Operating Activities")
    for year in range(2020, 2026):
        aliases[
            _label_page_year_alias_key(
                page_number=162,
                value_year=year,
                normalized_label=long_term_finance,
            )
        ] = "long_term_debt_summary_reference"
    for year in (2024, 2025):
        aliases[
            _label_page_year_alias_key(
                page_number=162,
                value_year=year,
                normalized_label=operating_cash_flow,
            )
        ] = "operating_cash_flow_summary_reference"
    return aliases


def _label_page_year_alias_key(
    *,
    page_number: int,
    value_year: int,
    normalized_label: str,
) -> str:
    return f"{page_number}|{value_year}|{normalized_label}"


__all__ = [
    "LUCKY_PRODUCTION_WORKBOOK_FINGERPRINT",
    "OCRV2BridgeConfig",
    "OCRV2BridgePageRange",
    "default_ocr_v2_bridge_config",
    "normalize_bridge_label",
]
