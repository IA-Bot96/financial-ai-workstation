"""Pipeline status values for OCR workflow execution."""

from enum import Enum


class PipelineStatus(str, Enum):
    """Lifecycle states for the OCR pipeline."""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
