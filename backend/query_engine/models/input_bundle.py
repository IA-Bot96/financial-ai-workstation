"""Versioned Query Engine input bundle models."""

from __future__ import annotations

import re
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator

from ocr_engine.models.insights_extraction import InsightsExtractionResult
from shared.models.financial_year_consolidation import (
    FinancialYearConsolidationResult,
)
from workbook_population.models.workbook_cell_mapping import WorkbookCellMappingRecord
from workbook_population.models.workbook_result import WorkbookResult

QUERY_ENGINE_INPUT_SCHEMA_VERSION = "1.0.0"


class BundleVersionInfo(BaseModel):
    """Parsed schema-version metadata for Query Engine input bundles."""

    model_config = ConfigDict(extra="forbid")

    schema_version: str = Field(..., min_length=1, description="Bundle schema version.")
    current_schema_version: str = Field(
        default=QUERY_ENGINE_INPUT_SCHEMA_VERSION,
        description="Highest schema version supported by this implementation.",
    )
    major: int = Field(..., ge=0, description="Schema major version.")
    minor: int = Field(..., ge=0, description="Schema minor version.")
    patch: int = Field(..., ge=0, description="Schema patch version.")
    is_compatible: bool = Field(
        ..., description="Whether this implementation can safely read the bundle."
    )
    warning: str | None = Field(
        default=None, description="Compatibility warning for newer minor versions."
    )

    @classmethod
    def parse(cls, schema_version: str) -> "BundleVersionInfo":
        """Parse a semantic schema version into compatibility metadata."""

        match = re.fullmatch(r"(\d+)\.(\d+)\.(\d+)", schema_version.strip())
        if match is None:
            return cls(
                schema_version=schema_version,
                major=0,
                minor=0,
                patch=0,
                is_compatible=False,
                warning="schema_version must use MAJOR.MINOR.PATCH format",
            )

        major, minor, patch = (int(part) for part in match.groups())
        current_major, current_minor, _ = (
            int(part) for part in QUERY_ENGINE_INPUT_SCHEMA_VERSION.split(".")
        )
        compatible = major == current_major
        warning = None
        if compatible and minor > current_minor:
            warning = (
                "Bundle uses a newer minor schema version; unknown optional "
                "fields may be ignored by this implementation."
            )

        return cls(
            schema_version=schema_version,
            major=major,
            minor=minor,
            patch=patch,
            is_compatible=compatible,
            warning=warning,
        )


class BundleValidationResult(BaseModel):
    """Validation result returned by bundle validators and loaders."""

    model_config = ConfigDict(extra="forbid")

    is_valid: bool = Field(..., description="Whether the bundle can be loaded.")
    errors: list[str] = Field(default_factory=list, description="Blocking errors.")
    warnings: list[str] = Field(default_factory=list, description="Non-blocking warnings.")
    version_info: BundleVersionInfo = Field(
        ..., description="Parsed bundle schema-version metadata."
    )


class QueryEngineInputBundle(BaseModel):
    """Structured handoff from OCR Engine v1 to the Financial Query Engine."""

    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={
            "examples": [
                {
                    "schema_version": QUERY_ENGINE_INPUT_SCHEMA_VERSION,
                    "workbook_id": "wb_8f6e0e4d8a9b",
                    "workbook_fingerprint": "8f6e0e4d8a9b",
                    "company_name": "Lucky Cement Limited",
                    "report_years": [2025],
                    "workbook_result": {
                        "output_file_path": "output/lucky.xlsx",
                        "workbook_mode": "dynamic",
                        "workbook_match_score": 0,
                        "sheets_reused": [],
                        "sheets_replaced": [],
                        "sheets_created": ["Income Statement"],
                        "metrics_written": 1,
                        "warnings": [],
                    },
                    "financial_year_consolidation_result": {
                        "metric_values": [],
                        "groups": [],
                    },
                    "insights_results_by_report_year": {},
                    "workbook_cell_mappings": [],
                }
            ]
        },
    )

    schema_version: str = Field(
        default=QUERY_ENGINE_INPUT_SCHEMA_VERSION,
        min_length=1,
        description="Version of the Query Engine input-bundle schema.",
    )
    workbook_id: str = Field(..., min_length=1, description="Stable workbook id.")
    workbook_fingerprint: str = Field(
        ..., min_length=1, description="Hash binding workbook bytes and sidecar data."
    )
    company_name: str = Field(..., min_length=1, description="Company name.")
    report_years: list[int] = Field(
        ..., min_length=1, description="Unique report years included in the bundle."
    )
    workbook_result: WorkbookResult = Field(
        ..., description="Workbook population output metadata."
    )
    financial_year_consolidation_result: FinancialYearConsolidationResult = Field(
        ..., description="Consolidated financial values and conflict diagnostics."
    )
    insights_results_by_report_year: dict[int, InsightsExtractionResult] = Field(
        ..., description="Insights extraction results keyed by source report year."
    )
    workbook_cell_mappings: list[WorkbookCellMappingRecord] = Field(
        ..., description="Authoritative metric-value-to-cell mappings."
    )

    @model_validator(mode="after")
    def _validate_bundle(self) -> "QueryEngineInputBundle":
        """Validate cross-field invariants for the handoff bundle."""

        version_info = BundleVersionInfo.parse(self.schema_version)
        if not version_info.is_compatible:
            raise ValueError(
                f"unsupported Query Engine input bundle schema: {self.schema_version}"
            )

        duplicate_years = sorted(
            year for year in set(self.report_years) if self.report_years.count(year) > 1
        )
        if duplicate_years:
            raise ValueError(f"report_years contains duplicates: {duplicate_years}")
        self.report_years = sorted(self.report_years)

        report_year_set = set(self.report_years)
        insight_years = set(self.insights_results_by_report_year)
        unknown_insight_years = insight_years - report_year_set
        if unknown_insight_years:
            raise ValueError(
                "insights_results_by_report_year contains years not present in "
                f"report_years: {sorted(unknown_insight_years)}"
            )

        for metric_value in self.financial_year_consolidation_result.metric_values:
            if metric_value.value_year > metric_value.source_report_year:
                raise ValueError(
                    "financial_year_consolidation_result contains a metric value "
                    "where value_year is greater than source_report_year"
                )

        for mapping in self.workbook_cell_mappings:
            if mapping.workbook_fingerprint != self.workbook_fingerprint:
                raise ValueError(
                    "workbook_cell_mappings contains a fingerprint that does not "
                    "match workbook_fingerprint"
                )

        return self

    def validate_contract(self) -> BundleValidationResult:
        """Return load-time validation diagnostics without mutating the bundle."""

        errors: list[str] = []
        warnings: list[str] = []
        version_info = BundleVersionInfo.parse(self.schema_version)
        if not version_info.is_compatible:
            errors.append(f"unsupported schema_version: {self.schema_version}")
        if version_info.warning:
            warnings.append(version_info.warning)

        if not self.workbook_cell_mappings:
            warnings.append("workbook_cell_mappings is empty; cell citations unavailable")
        if not self.financial_year_consolidation_result.metric_values:
            warnings.append(
                "financial_year_consolidation_result.metric_values is empty"
            )

        mapping_keys = {
            (
                mapping.metric,
                mapping.value_year,
                mapping.source_report_year,
                mapping.table_type,
            )
            for mapping in self.workbook_cell_mappings
            if mapping.write_status == "written"
        }
        for metric_value in self.financial_year_consolidation_result.metric_values:
            key = (
                metric_value.metric,
                metric_value.value_year,
                metric_value.source_report_year,
                metric_value.table_type,
            )
            if mapping_keys and key not in mapping_keys:
                warnings.append(
                    "missing written workbook cell mapping for "
                    f"{metric_value.metric}/{metric_value.value_year}/"
                    f"{metric_value.source_report_year}/{metric_value.table_type}"
                )

        return BundleValidationResult(
            is_valid=not errors,
            errors=errors,
            warnings=_deduplicate(warnings),
            version_info=version_info,
        )

    def stable_payload(self) -> dict[str, Any]:
        """Return the bundle payload with volatile fingerprint fields removed."""

        payload = self.model_dump(mode="json")
        payload["workbook_id"] = ""
        payload["workbook_fingerprint"] = ""
        for mapping in payload["workbook_cell_mappings"]:
            mapping["workbook_fingerprint"] = ""
        return payload


def _deduplicate(values: list[str]) -> list[str]:
    seen: set[str] = set()
    deduplicated: list[str] = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        deduplicated.append(value)
    return deduplicated


__all__ = [
    "BundleValidationResult",
    "BundleVersionInfo",
    "QUERY_ENGINE_INPUT_SCHEMA_VERSION",
    "QueryEngineInputBundle",
]
