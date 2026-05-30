"""Exceptions for OpenAI-backed OCR services."""


class MissingOpenAIConfigurationError(RuntimeError):
    """Raised when OpenAI configuration is missing or still using a dummy key."""


class OpenAITableClassificationError(RuntimeError):
    """Raised when table classification fails after retry attempts."""


class OpenAIInsightsExtractionError(RuntimeError):
    """Raised when insights extraction fails after retry attempts."""


class OpenAIResponseValidationError(ValueError):
    """Raised when OpenAI returns JSON that does not match the expected schema."""
