"""Pipeline error model for failed OCR workflow layers."""

from pydantic import BaseModel, ConfigDict, Field


class PipelineError(BaseModel):
    """Failure captured from a single OCR pipeline layer."""

    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={
            "examples": [
                {
                    "layer_name": "Table Extraction",
                    "error_message": "Camelot is required for table extraction.",
                }
            ]
        },
    )

    layer_name: str = Field(
        ...,
        min_length=1,
        description="Name of the OCR pipeline layer that failed.",
        examples=["Table Extraction"],
    )
    error_message: str = Field(
        ...,
        min_length=1,
        description="Human-readable error message captured from the failed layer.",
        examples=["Camelot is required for table extraction."],
    )
