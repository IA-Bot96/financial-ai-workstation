"""Configuration values for OCR table detection."""

from shared.config.settings import get_settings

_settings = get_settings()

TABLE_DETECTION_CONFIDENCE_THRESHOLD = (
    _settings.table_detection_confidence_threshold
)
TABLE_DETECTION_MODEL_NAME = _settings.table_transformer_model
