"""Unit tests for runtime settings validation."""

import sys
from pathlib import Path

import pytest

BACKEND_DIR = Path(__file__).resolve().parents[2]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from shared.config.settings import ConfigurationError, ConfigurationValidator, Settings


def test_configuration_validator_requires_openai_key(tmp_path: Path) -> None:
    settings = Settings(
        OPENAI_API_KEY="",
        OUTPUT_DIRECTORY=tmp_path,
        _env_file=None,
    )

    with pytest.raises(ConfigurationError, match="OPENAI_API_KEY is required"):
        ConfigurationValidator(settings).validate_openai_api_key()


def test_configuration_validator_creates_output_directory(tmp_path: Path) -> None:
    output_directory = tmp_path / "output"
    settings = Settings(
        OPENAI_API_KEY="sk-test",
        OUTPUT_DIRECTORY=output_directory,
        _env_file=None,
    )

    result = ConfigurationValidator(settings).ensure_output_directory()

    assert result == output_directory
    assert output_directory.is_dir()


def test_configuration_validator_rejects_missing_local_model_path(
    tmp_path: Path,
) -> None:
    missing_model_path = tmp_path / "missing-model"

    with pytest.raises(ConfigurationError, match="path does not exist"):
        ConfigurationValidator.validate_model_reference(str(missing_model_path))
