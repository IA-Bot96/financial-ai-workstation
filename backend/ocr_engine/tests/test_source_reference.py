"""Unit tests for the source reference model."""

import sys
from pathlib import Path

import pytest
from pydantic import ValidationError

BACKEND_DIR = Path(__file__).resolve().parents[2]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from ocr_engine.models.source_reference import SourceReference


def test_source_reference_accepts_valid_payload() -> None:
    source = SourceReference(
        year=2024,
        section="Management Discussion & Analysis",
        page_number=84,
    )

    assert source.model_dump() == {
        "year": 2024,
        "section": "Management Discussion & Analysis",
        "page_number": 84,
    }


def test_source_reference_requires_positive_page() -> None:
    with pytest.raises(ValidationError) as exc_info:
        SourceReference(
            year=2024,
            section="Management Discussion & Analysis",
            page_number=0,
        )

    assert exc_info.value.errors()[0]["type"] == "greater_than"


def test_source_reference_forbids_extra_fields() -> None:
    with pytest.raises(ValidationError) as exc_info:
        SourceReference(
            year=2024,
            section="Management Discussion & Analysis",
            page_number=84,
            paragraph=3,
        )

    assert exc_info.value.errors()[0]["type"] == "extra_forbidden"
