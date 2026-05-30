"""Custom exceptions raised by OCR engine services."""

from .openai_exceptions import (
    MissingOpenAIConfigurationError,
    OpenAIInsightsExtractionError,
    OpenAITableClassificationError,
    OpenAIResponseValidationError,
)

__all__ = [
    "MissingOpenAIConfigurationError",
    "OpenAIInsightsExtractionError",
    "OpenAITableClassificationError",
    "OpenAIResponseValidationError",
]
