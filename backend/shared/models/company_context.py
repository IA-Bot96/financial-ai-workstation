"""Shared company context model for multi-year report processing."""

from pydantic import BaseModel, ConfigDict, Field, model_validator

from ocr_engine.models.financial_table_classification import (
    FinancialTableClassificationResult,
)
from ocr_engine.models.insights_extraction import InsightsExtractionResult
from ocr_engine.models.table_detection_result import TableDetectionResult
from ocr_engine.models.table_extraction import TableExtractionResult
from ocr_engine.models.table_normalization import NormalizationResult
from ocr_engine.models.validation_result import ValidationResult
from ocr_engine.pipeline.models.layer_execution_result import LayerExecutionResult
from ocr_engine.pipeline.models.pipeline_error import PipelineError
from ocr_engine.pipeline.models.pipeline_status import PipelineStatus
from shared.models.financial_year_consolidation import FinancialYearConsolidationResult
from shared.models.metric_value import MetricValue
from shared.models.report import Report
from workbook_population.models.workbook_result import WorkbookResult


class CompanyContext(BaseModel):
    """Aggregated multi-year OCR context for one company."""

    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={
            "examples": [
                {
                    "company_name": "Maple Leaf Cement Factory Limited",
                    "reports": [
                        {
                            "id": "rpt_2024_001",
                            "company_name": "Maple Leaf Cement Factory Limited",
                            "year": 2024,
                            "file_name": "MLCF_2024_Annual_Report.pdf",
                            "file_path": "/reports/MLCF_2024_Annual_Report.pdf",
                        }
                    ],
                    "table_detection_results": {},
                    "classification_results": {},
                    "extraction_results": {},
                    "validation_results": {},
                    "normalization_results": {},
                    "insights_results": {},
                    "metric_values": [],
                    "financial_year_consolidation_result": None,
                    "workbook_template_path": None,
                    "workbook_result": None,
                    "generated_workbook": None,
                    "query_engine_bundle_path": None,
                    "query_engine_bundle_validation": {},
                    "pipeline_status": "pending",
                    "pipeline_errors": [],
                    "execution_results": [],
                }
            ]
        },
    )

    company_name: str = Field(
        ...,
        min_length=1,
        description="Company represented by this multi-year context.",
        examples=["Maple Leaf Cement Factory Limited"],
    )
    reports: list[Report] = Field(
        ...,
        description="Annual reports processed for the company.",
    )
    table_detection_results: dict[int, TableDetectionResult] = Field(
        default_factory=dict,
        description="Table detection results keyed by financial reporting year.",
    )
    classification_results: dict[int, FinancialTableClassificationResult] = Field(
        default_factory=dict,
        description="Financial table classifications keyed by reporting year.",
    )
    extraction_results: dict[int, TableExtractionResult] = Field(
        default_factory=dict,
        description="Table extraction results keyed by reporting year.",
    )
    validation_results: dict[int, ValidationResult] = Field(
        default_factory=dict,
        description="Validation results keyed by reporting year.",
    )
    normalization_results: dict[int, NormalizationResult] = Field(
        default_factory=dict,
        description="OCR normalization results keyed by reporting year.",
    )
    insights_results: dict[int, InsightsExtractionResult] = Field(
        default_factory=dict,
        description="Business insights extraction results keyed by reporting year.",
    )
    metric_values: list[MetricValue] = Field(
        default_factory=list,
        description=(
            "Consolidated financial metric values used by Excel population, "
            "trend analysis, querying, forecasting, charting, and copilots."
        ),
    )
    financial_year_consolidation_result: FinancialYearConsolidationResult | None = (
        Field(
            default=None,
            description=(
                "Auditable financial-year consolidation output, including selected "
                "values, competing candidates, conflict status, and resolution "
                "provenance."
            ),
        )
    )
    workbook_template_path: str | None = Field(
        default=None,
        description="Optional accountant-built Excel template path for workbook population.",
        examples=["/templates/MLCF_Template.xlsx"],
    )
    workbook_result: WorkbookResult | None = Field(
        default=None,
        description="Workbook population layer output retained for backward compatibility.",
    )
    generated_workbook: WorkbookResult | None = Field(
        default=None,
        description=(
            "Final generated Excel workbook metadata exposed to Electron, "
            "FastAPI, Query Engine, and future services."
        ),
    )
    query_engine_bundle_path: str | None = Field(
        default=None,
        description=(
            "Path to the serialized Query Engine input bundle generated after "
            "workbook population."
        ),
    )
    query_engine_bundle_validation: dict[str, object] = Field(
        default_factory=dict,
        description="Validation result for the generated Query Engine input bundle.",
    )
    pipeline_status: PipelineStatus = Field(
        default=PipelineStatus.PENDING,
        description="Current lifecycle status of the OCR pipeline.",
        examples=[PipelineStatus.PENDING],
    )
    pipeline_errors: list[PipelineError] = Field(
        default_factory=list,
        description="Errors captured from failed OCR pipeline layers.",
    )
    execution_results: list[LayerExecutionResult] = Field(
        default_factory=list,
        description="Execution timing and success telemetry for OCR pipeline layers.",
    )

    @model_validator(mode="after")
    def _validate_year_keys(self) -> "CompanyContext":
        """Ensure result dictionaries are keyed by known report years."""

        report_years = [report.year for report in self.reports]
        duplicate_years = sorted(
            year for year in set(report_years) if report_years.count(year) > 1
        )
        if duplicate_years:
            raise ValueError(f"reports contain duplicate years: {duplicate_years}")

        unknown_companies = {
            report.company_name
            for report in self.reports
            if report.company_name != self.company_name
        }
        if unknown_companies:
            raise ValueError(
                "reports contain company names different from company_name: "
                f"{sorted(unknown_companies)}"
            )

        report_year_set = set(report_years)
        for field_name in (
            "table_detection_results",
            "classification_results",
            "extraction_results",
            "validation_results",
            "normalization_results",
            "insights_results",
        ):
            result_years = set(getattr(self, field_name))
            unknown_years = result_years - report_year_set
            if unknown_years:
                raise ValueError(
                    f"{field_name} contains years not present in reports: "
                    f"{sorted(unknown_years)}"
                )

        metric_source_years = {
            metric_value.source_report_year for metric_value in self.metric_values
        }
        unknown_metric_source_years = metric_source_years - report_year_set
        if unknown_metric_source_years:
            raise ValueError(
                "metric_values contain source_report_year values not present "
                f"in reports: {sorted(unknown_metric_source_years)}"
            )

        return self
