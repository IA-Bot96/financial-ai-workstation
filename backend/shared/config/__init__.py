"""Shared runtime configuration for the OCR platform."""

from .settings import ConfigurationError, ConfigurationValidator, Settings, get_settings

__all__ = [
    "ConfigurationError",
    "ConfigurationValidator",
    "Settings",
    "get_settings",
]
