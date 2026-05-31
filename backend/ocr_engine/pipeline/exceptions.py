"""Internal exceptions used by OCR pipeline orchestration."""

from __future__ import annotations

from typing import Any


class PipelineLayerPartialFailure(RuntimeError):
    """Raised when a layer processes some years and skips failed years."""

    def __init__(self, error_messages: list[str], *, context: Any) -> None:
        """Store year-level failures while preserving the updated context."""

        if not error_messages:
            raise ValueError("error_messages must contain at least one message.")

        self.error_messages = error_messages
        self.context = context
        super().__init__("; ".join(error_messages))
