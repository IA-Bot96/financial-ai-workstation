"""Versioned workbook cell mapping records for Query Engine handoff."""

from __future__ import annotations

import re
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


WorkbookWriteStatus = Literal[
    "written",
    "skipped_formula",
    "mapping_missing",
    "conflict_replaced",
]


class WorkbookCellMappingDraft(BaseModel):
    """Authoritative workbook destination captured while writing a workbook.

    The workbook fingerprint is assigned after the final workbook bytes and
    structured payload are hashed, so writer services capture drafts first and
    the Query Engine bundle generator promotes them to versioned records.
    """

    model_config = ConfigDict(extra="forbid")

    metric: str = Field(..., min_length=1, description="Canonical metric key.")
    value_year: int = Field(..., ge=1900, description="Financial year represented.")
    source_report_year: int = Field(
        ..., ge=1900, description="Annual report year that supplied the value."
    )
    table_type: str = Field(..., min_length=1, description="Source table type.")
    sheet_name: str = Field(..., min_length=1, description="Workbook sheet name.")
    row: int = Field(..., gt=0, description="One-based worksheet row.")
    column: int = Field(..., gt=0, description="One-based worksheet column.")
    cell_reference: str = Field(
        ..., min_length=1, description="Excel cell coordinate, for example C12."
    )
    write_status: WorkbookWriteStatus = Field(
        ..., description="Workbook write outcome for this destination."
    )
    written_value: float | int | str | None = Field(
        default=None, description="Value written or attempted for this cell."
    )

    @model_validator(mode="after")
    def _validate_years_and_cell(self) -> "WorkbookCellMappingDraft":
        """Validate year ordering and Excel-style cell references."""

        if self.value_year > self.source_report_year:
            raise ValueError("value_year must be less than or equal to source_report_year")
        if not re.fullmatch(r"[A-Z]{1,3}[1-9][0-9]*", self.cell_reference):
            raise ValueError("cell_reference must be an Excel cell coordinate")
        return self

    def to_record(self, workbook_fingerprint: str) -> "WorkbookCellMappingRecord":
        """Promote this draft to a persisted versioned mapping record."""

        return WorkbookCellMappingRecord(
            workbook_fingerprint=workbook_fingerprint,
            **self.model_dump(),
        )


class WorkbookCellMappingRecord(WorkbookCellMappingDraft):
    """Persisted authoritative mapping between a metric value and workbook cell."""

    workbook_fingerprint: str = Field(
        ..., min_length=1, description="Fingerprint of the workbook and sidecar."
    )


__all__ = [
    "WorkbookCellMappingDraft",
    "WorkbookCellMappingRecord",
    "WorkbookWriteStatus",
]
