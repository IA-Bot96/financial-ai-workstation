"""Pipeline layer execution timing model."""

from pydantic import BaseModel, ConfigDict, Field


class LayerExecutionResult(BaseModel):
    """Execution telemetry for one OCR pipeline layer."""

    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={
            "examples": [
                {
                    "layer_name": "Table Detection",
                    "execution_time_seconds": 12.47,
                    "success": True,
                }
            ]
        },
    )

    layer_name: str = Field(
        ...,
        min_length=1,
        description="Name of the OCR pipeline layer that was executed.",
        examples=["Table Detection"],
    )
    execution_time_seconds: float = Field(
        ...,
        ge=0,
        description="Wall-clock execution time for the layer in seconds.",
        examples=[12.47],
    )
    success: bool = Field(
        ...,
        description="Whether the layer completed without raising an exception.",
        examples=[True],
    )
