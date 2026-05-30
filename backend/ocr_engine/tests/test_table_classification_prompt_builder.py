"""Unit tests for the table classification prompt builder."""

import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[2]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from ocr_engine.services.prompt_builders.table_classification_prompt_builder import (
    TableClassificationPromptBuilder,
)


def test_table_classification_prompt_builder_includes_page_context() -> None:
    builder = TableClassificationPromptBuilder()

    messages = builder.build_messages(
        page_number=20,
        tables_detected=2,
        page_text="Statement of Financial Position\nLong term financing",
    )

    assert messages[0]["role"] == "system"
    assert messages[1]["role"] == "user"
    assert "Page number: 20" in messages[1]["content"]
    assert "Tables detected on page: 2" in messages[1]["content"]
    assert "Statement of Financial Position" in messages[1]["content"]
    assert "Return ONLY JSON" in messages[1]["content"]
