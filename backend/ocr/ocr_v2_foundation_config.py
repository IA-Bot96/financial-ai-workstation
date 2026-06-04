"""Immutable OCR V2 foundation configuration definitions.

Configuration only. This module does not implement governance, scale
normalization, entity resolution, candidate capture, or selection behavior.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from .ocr_v2_contracts import OCRV2Basis, OCRV2EntityScope, OCRV2StatementType


class OCRV2FoundationConfig(BaseModel):
    """Frozen config shape consumed by future OCR V2 phases."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    declared_basis: OCRV2Basis = OCRV2Basis.UNCONSOLIDATED
    target_scale: str = Field(default="source_declared_target", min_length=1)
    statement_type_enum: tuple[OCRV2StatementType, ...] = Field(
        default_factory=lambda: tuple(OCRV2StatementType)
    )
    entity_scope_enum: tuple[OCRV2EntityScope, ...] = Field(
        default_factory=lambda: tuple(OCRV2EntityScope)
    )


def default_ocr_v2_foundation_config() -> OCRV2FoundationConfig:
    """Return the immutable default OCR V2 foundation config."""

    return OCRV2FoundationConfig()


__all__ = ["OCRV2FoundationConfig", "default_ocr_v2_foundation_config"]
