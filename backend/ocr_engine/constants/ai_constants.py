"""Configuration values for AI-backed OCR services."""

from shared.config.settings import get_settings

_settings = get_settings()

OPENAI_API_KEY = _settings.openai_api_key
OPENAI_MODEL = _settings.openai_model
OPENAI_CLASSIFICATION_MAX_RETRIES = _settings.openai_classification_max_retries
OPENAI_CLASSIFICATION_RETRY_BACKOFF_SECONDS = (
    _settings.openai_classification_retry_backoff_seconds
)
OPENAI_INSIGHTS_MAX_RETRIES = _settings.openai_insights_max_retries
OPENAI_INSIGHTS_RETRY_BACKOFF_SECONDS = (
    _settings.openai_insights_retry_backoff_seconds
)
