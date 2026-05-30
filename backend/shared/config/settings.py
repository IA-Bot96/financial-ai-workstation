"""Runtime settings and startup validation for the OCR platform."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class ConfigurationError(RuntimeError):
    """Raised when required runtime configuration is missing or invalid."""


class Settings(BaseSettings):
    """Environment-backed OCR platform settings."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    openai_api_key: str | None = Field(default=None, alias="OPENAI_API_KEY")
    openai_model: str = Field(default="gpt-5", alias="OPENAI_MODEL")
    table_transformer_model: str = Field(
        default="microsoft/table-transformer-detection",
        alias="TABLE_TRANSFORMER_MODEL",
    )
    table_detection_confidence_threshold: float = Field(
        default=0.90,
        ge=0,
        le=1,
        alias="TABLE_DETECTION_CONFIDENCE_THRESHOLD",
    )
    log_level: str = Field(default="INFO", alias="LOG_LEVEL")
    output_directory: Path = Field(default=Path("output"), alias="OUTPUT_DIRECTORY")
    openai_classification_max_retries: int = Field(
        default=3,
        ge=1,
        alias="OPENAI_CLASSIFICATION_MAX_RETRIES",
    )
    openai_classification_retry_backoff_seconds: float = Field(
        default=1.0,
        ge=0,
        alias="OPENAI_CLASSIFICATION_RETRY_BACKOFF_SECONDS",
    )
    openai_insights_max_retries: int = Field(
        default=3,
        ge=1,
        alias="OPENAI_INSIGHTS_MAX_RETRIES",
    )
    openai_insights_retry_backoff_seconds: float = Field(
        default=1.0,
        ge=0,
        alias="OPENAI_INSIGHTS_RETRY_BACKOFF_SECONDS",
    )

    @field_validator("openai_api_key")
    @classmethod
    def _strip_openai_api_key(cls, value: str | None) -> str | None:
        if value is None:
            return None
        stripped = value.strip()
        return stripped or None

    @field_validator("openai_model", "table_transformer_model", "log_level")
    @classmethod
    def _non_empty_string(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("configuration value cannot be empty")
        return stripped


class ConfigurationValidator:
    """Validate settings before expensive OCR dependencies are initialized."""

    _PLACEHOLDER_OPENAI_KEYS = {
        "changeme",
        "replace_me",
        "your_openai_api_key",
        "your-api-key",
    }

    def __init__(self, settings: Settings | None = None) -> None:
        """Initialize the validator with optional injected settings."""

        self._settings = settings or get_settings()

    def validate_startup(self) -> None:
        """Validate all required startup configuration."""

        self.validate_openai_api_key()
        self.ensure_output_directory()
        self.validate_model_reference(self._settings.table_transformer_model)

    def validate_openai_api_key(self) -> None:
        """Ensure the OpenAI API key is present and not a placeholder."""

        api_key = self._settings.openai_api_key
        if not api_key:
            raise ConfigurationError("OPENAI_API_KEY is required.")

        if api_key.strip().lower() in self._PLACEHOLDER_OPENAI_KEYS:
            raise ConfigurationError("OPENAI_API_KEY must not be a placeholder value.")

    def ensure_output_directory(self) -> Path:
        """Ensure the configured output directory exists and is writable."""

        output_directory = self._settings.output_directory
        output_directory.mkdir(parents=True, exist_ok=True)
        if not output_directory.is_dir():
            raise ConfigurationError(
                f"OUTPUT_DIRECTORY is not a directory: {output_directory}"
            )

        probe = output_directory / ".write_check"
        try:
            probe.write_text("ok", encoding="utf-8")
            probe.unlink()
        except OSError as exc:
            raise ConfigurationError(
                f"OUTPUT_DIRECTORY is not writable: {output_directory}"
            ) from exc

        return output_directory

    @staticmethod
    def validate_model_reference(model_reference: str) -> None:
        """Validate a Hugging Face model name or local model path reference."""

        stripped = model_reference.strip()
        if not stripped:
            raise ConfigurationError("TABLE_TRANSFORMER_MODEL is required.")

        model_path = Path(stripped)
        looks_like_local_path = (
            model_path.is_absolute()
            or stripped.startswith(".")
            or "\\" in stripped
        )
        if looks_like_local_path and not model_path.exists():
            raise ConfigurationError(
                f"TABLE_TRANSFORMER_MODEL path does not exist: {model_path}"
            )


@lru_cache
def get_settings() -> Settings:
    """Return cached environment-backed settings."""

    return Settings()
