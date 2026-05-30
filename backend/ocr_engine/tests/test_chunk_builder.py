"""Unit tests for narrative chunk construction."""

import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[2]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from ocr_engine.services.chunk_builder import ChunkBuilder
from ocr_engine.services.section_identifier import SectionPage


def test_chunk_builder_preserves_source_traceability() -> None:
    builder = ChunkBuilder(max_characters=500, overlap_characters=50)

    chunks = builder.build_chunks(
        [
            SectionPage(
                page_number=84,
                section="Management Discussion & Analysis",
                text="Debt increased due to capacity expansion.\n\nExports improved.",
            )
        ]
    )

    assert len(chunks) == 1
    assert chunks[0].page_number == 84
    assert chunks[0].source_section == "Management Discussion & Analysis"
    assert "Debt increased" in chunks[0].text
