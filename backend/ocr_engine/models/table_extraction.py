"""Models for OCR table extraction results."""

from pydantic import AliasChoices, BaseModel, ConfigDict, Field

from ocr_engine.models.table_detection_result import BBox
from shared.models.metric_value import MetricValue


class PageExtractionDiagnostic(BaseModel):
    """Per-page extraction linkage diagnostics."""

    model_config = ConfigDict(extra="forbid")

    source_report_year: int = Field(
        ...,
        ge=1900,
        description="Annual report year for this page diagnostic.",
        examples=[2025],
    )
    page_number: int = Field(
        ...,
        gt=0,
        description="One-based PDF page number being diagnosed.",
        examples=[20],
    )
    detected_table_count: int = Field(
        ...,
        ge=0,
        description="Number of tables reported by the detection layer.",
        examples=[2],
    )
    classified_table_count: int = Field(
        ...,
        ge=0,
        description="Number of table types returned by classification.",
        examples=[2],
    )
    extracted_table_count: int = Field(
        ...,
        ge=0,
        description="Number of raw tables extracted from the page.",
        examples=[2],
    )
    matched_table_count: int = Field(
        ...,
        ge=0,
        description="Number of extracted tables matched to classified table types.",
        examples=[2],
    )
    extraction_strategy: str = Field(
        default="unknown",
        min_length=1,
        description="Extraction strategy selected for this page.",
        examples=["full_page_pdfplumber_text"],
    )
    quality_score: float = Field(
        default=0.0,
        ge=0,
        le=100,
        description="Extraction quality score from 0 to 100.",
        examples=[87.5],
    )
    year_column_count: int = Field(
        default=0,
        ge=0,
        description="Number of detected year columns in the selected extraction.",
        examples=[2],
    )
    metric_label_count: int = Field(
        default=0,
        ge=0,
        description="Number of detected metric label rows in the selected extraction.",
        examples=[15],
    )
    metric_value_count: int = Field(
        default=0,
        ge=0,
        description="Number of MetricValues generated from the selected extraction.",
        examples=[15],
    )
    numeric_only_table_count: int = Field(
        default=0,
        ge=0,
        description="Number of selected extracted tables that contain numbers but no labels.",
        examples=[0],
    )
    unmatched_classifications: list[str] = Field(
        default_factory=list,
        description="Classified table types that did not match an extracted table.",
        examples=[["income_statement"]],
    )
    unmatched_extractions: list[int] = Field(
        default_factory=list,
        description="Extracted table indexes that did not match a classification.",
        examples=[[1]],
    )
    tables_split: int = Field(
        default=0,
        ge=0,
        description="Number of additional logical tables created by scoped splitting.",
        examples=[2],
    )
    split_reason: str | None = Field(
        default=None,
        description="Reason code for scoped table splitting on this page.",
        examples=["analysis_section_markers_with_repeated_year_headers"],
    )
    logical_types_created: list[str] = Field(
        default_factory=list,
        description="Logical table types created by scoped table splitting.",
        examples=[["balance_sheet", "vertical_analysis", "horizontal_analysis"]],
    )
    id_matches: int = Field(
        default=0,
        ge=0,
        description="Number of matches made by detected_table_id equality.",
        examples=[2],
    )
    bbox_matches: int = Field(
        default=0,
        ge=0,
        description="Number of matches made by bounding-box IoU or containment.",
        examples=[1],
    )
    order_matches: int = Field(
        default=0,
        ge=0,
        description="Number of matches made by page-level extraction order.",
        examples=[1],
    )
    fallback_matches: int = Field(
        default=0,
        ge=0,
        description="Number of matches made by text-similarity fallback.",
        examples=[1],
    )
    previously_unclassified_tables_recovered: int = Field(
        default=0,
        ge=0,
        description=(
            "Tables assigned a classification by identity/bbox/order matching "
            "that would otherwise have remained unclassified by text fallback."
        ),
        examples=[1],
    )
    metric_values_recovered: int = Field(
        default=0,
        ge=0,
        description="MetricValues carried by recovered table assignments.",
        examples=[24],
    )


class SuspiciousTableFinding(BaseModel):
    """A table-level extraction quality issue for review."""

    model_config = ConfigDict(extra="forbid")

    source_report_year: int = Field(
        ...,
        ge=1900,
        description="Annual report year from which the table was extracted.",
        examples=[2025],
    )
    page_number: int = Field(
        ...,
        gt=0,
        description="One-based PDF page number where the table was extracted.",
        examples=[225],
    )
    table_index: int = Field(
        ...,
        ge=0,
        description="Zero-based table index on the source PDF page.",
        examples=[0],
    )
    table_type: str = Field(
        ...,
        min_length=1,
        description="Assigned financial table type.",
        examples=["unclassified_table"],
    )
    row_count: int = Field(
        ...,
        ge=0,
        description="Number of extracted rows in the table.",
        examples=[14],
    )
    column_count: int = Field(
        ...,
        ge=0,
        description="Maximum number of extracted columns in the table.",
        examples=[3],
    )
    quality_score: float = Field(
        ...,
        ge=0,
        le=100,
        description="Table-level extraction quality score from 0 to 100.",
        examples=[32.0],
    )
    suspicion_score: float = Field(
        ...,
        ge=0,
        le=100,
        description="Review priority score from 0 to 100.",
        examples=[82.0],
    )
    year_column_count: int = Field(
        ...,
        ge=0,
        description="Number of detected year columns in the table.",
        examples=[0],
    )
    metric_label_count: int = Field(
        ...,
        ge=0,
        description="Number of detected metric label rows in the table.",
        examples=[0],
    )
    metric_value_count: int = Field(
        ...,
        ge=0,
        description="Number of MetricValues generated from the table.",
        examples=[0],
    )
    numeric_only: bool = Field(
        ...,
        description="Whether the table contains numeric values but no labels.",
        examples=[True],
    )
    reasons: list[str] = Field(
        default_factory=list,
        description="Stable reason codes explaining why the table is suspicious.",
        examples=[["missing_years", "missing_labels", "numeric_only_table"]],
    )


class MetricValueOccurrence(BaseModel):
    """Trace reference for one extracted MetricValue occurrence."""

    model_config = ConfigDict(extra="forbid")

    page_number: int = Field(
        ...,
        gt=0,
        description="One-based PDF page number where the value originated.",
        examples=[225],
    )
    table_index: int = Field(
        ...,
        ge=0,
        description="Zero-based table index where the value originated.",
        examples=[0],
    )
    table_type: str = Field(
        ...,
        min_length=1,
        description="Financial table category where the value originated.",
        examples=["debt_schedule"],
    )
    value: float | int | str = Field(
        ...,
        description="Extracted metric value.",
        examples=[951736],
    )


class SuspiciousMetricFinding(BaseModel):
    """Metric-level extraction quality issue for review."""

    model_config = ConfigDict(extra="forbid")

    metric: str = Field(
        ...,
        min_length=1,
        description="Extracted metric label.",
        examples=["Long term loan"],
    )
    value_year: int = Field(
        ...,
        ge=1900,
        description="Financial year represented by the metric value.",
        examples=[2025],
    )
    source_report_year: int = Field(
        ...,
        ge=1900,
        description="Annual report year from which the value was sourced.",
        examples=[2025],
    )
    table_type: str = Field(
        ...,
        min_length=1,
        description="Financial table category where the value originated.",
        examples=["debt_schedule"],
    )
    occurrence_count: int = Field(
        ...,
        ge=1,
        description="Number of occurrences for the metric/year/table key.",
        examples=[2],
    )
    distinct_values: list[float | int | str] = Field(
        default_factory=list,
        description="Distinct extracted values for the metric key.",
        examples=[[951736, 950000]],
    )
    suspicion_score: float = Field(
        ...,
        ge=0,
        le=100,
        description="Review priority score from 0 to 100.",
        examples=[90.0],
    )
    reasons: list[str] = Field(
        default_factory=list,
        description="Stable reason codes explaining why the metric is suspicious.",
        examples=[["conflicting_values", "duplicate_metric_values"]],
    )
    occurrences: list[MetricValueOccurrence] = Field(
        default_factory=list,
        description="Trace references for occurrences contributing to the finding.",
    )


class LabelReconstructionDiagnostic(BaseModel):
    """Trace of a metric label reconstructed from adjacent table cells."""

    model_config = ConfigDict(extra="forbid")

    source_report_year: int = Field(
        ...,
        ge=1900,
        description="Annual report year from which the label was extracted.",
        examples=[2025],
    )
    page_number: int = Field(
        ...,
        gt=0,
        description="One-based PDF page number where the label was extracted.",
        examples=[225],
    )
    table_index: int = Field(
        ...,
        ge=0,
        description="Zero-based table index on the source page.",
        examples=[0],
    )
    table_type: str = Field(
        ...,
        min_length=1,
        description="Financial table category where the label originated.",
        examples=["balance_sheet"],
    )
    row_index: int = Field(
        ...,
        ge=0,
        description="Zero-based row index containing the reconstructed label.",
        examples=[3],
    )
    original_label: str = Field(
        ...,
        min_length=1,
        description="Original first label fragment selected by row parsing.",
        examples=["Fair value reserve - In"],
    )
    reconstructed_label: str = Field(
        ...,
        min_length=1,
        description="Label reconstructed by merging adjacent text cells.",
        examples=["Fair value reserve - Investments measured at FVOCI"],
    )
    reconstruction_confidence: float = Field(
        ...,
        ge=0,
        le=1,
        description="Confidence that adjacent cells were merged correctly.",
        examples=[0.95],
    )
    merged_cell_count: int = Field(
        ...,
        ge=1,
        description="Number of non-empty text cells used in the reconstructed label.",
        examples=[4],
    )
    metric_values_affected: int = Field(
        ...,
        ge=0,
        description="Number of MetricValues generated from this reconstructed row.",
        examples=[2],
    )
    stop_reason: str = Field(
        ...,
        min_length=1,
        description="Boundary condition that stopped label merging.",
        examples=["numeric_value"],
    )


class LabelDegluingDiagnostic(BaseModel):
    """Trace of a reconstructed label cleaned for intra-word spacing artifacts."""

    model_config = ConfigDict(extra="forbid")

    source_report_year: int = Field(
        ...,
        ge=1900,
        description="Annual report year from which the label was extracted.",
        examples=[2025],
    )
    page_number: int = Field(
        ...,
        gt=0,
        description="One-based PDF page number where the label was extracted.",
        examples=[225],
    )
    table_index: int = Field(
        ...,
        ge=0,
        description="Zero-based table index on the source page.",
        examples=[0],
    )
    table_type: str = Field(
        ...,
        min_length=1,
        description="Financial table category where the label originated.",
        examples=["balance_sheet"],
    )
    row_index: int = Field(
        ...,
        ge=0,
        description="Zero-based row index containing the deglued label.",
        examples=[3],
    )
    original_label: str = Field(
        ...,
        min_length=1,
        description="Label after reconstruction but before degluing.",
        examples=["Current Asse ts"],
    )
    deglued_label: str = Field(
        ...,
        min_length=1,
        description="Label after intra-word spacing artifacts were removed.",
        examples=["Current Assets"],
    )
    degluing_confidence: float = Field(
        ...,
        ge=0,
        le=1,
        description="Confidence that the degluing operation preserved the label.",
        examples=[0.97],
    )
    rules_applied: list[str] = Field(
        default_factory=list,
        description="Stable rule names applied during label degluing.",
        examples=[["known_financial_word_join"]],
    )
    metric_values_affected: int = Field(
        ...,
        ge=0,
        description="Number of MetricValues generated from this deglued row.",
        examples=[2],
    )


class FragmentationCleanupDiagnostic(BaseModel):
    """Trace of a fragmented metric label completed before MetricValue creation."""

    model_config = ConfigDict(extra="forbid")

    source_report_year: int = Field(
        ...,
        ge=1900,
        description="Annual report year from which the label was extracted.",
        examples=[2025],
    )
    page_number: int = Field(
        ...,
        gt=0,
        description="One-based PDF page number where the label was extracted.",
        examples=[164],
    )
    table_index: int = Field(
        ...,
        ge=0,
        description="Zero-based table index on the source page.",
        examples=[0],
    )
    table_type: str = Field(
        ...,
        min_length=1,
        description="Financial table category where the label originated.",
        examples=["income_statement"],
    )
    row_index: int = Field(
        ...,
        ge=0,
        description="Zero-based row index containing the completed label.",
        examples=[7],
    )
    original_label: str = Field(
        ...,
        min_length=1,
        description="Label after reconstruction/degluing and before final cleanup.",
        examples=["Property, plant a nd equipment"],
    )
    completed_label: str = Field(
        ...,
        min_length=1,
        description="Metric label after fragmentation cleanup.",
        examples=["Property, plant and equipment"],
    )
    reconstruction_reason: str = Field(
        ...,
        min_length=1,
        description="Stable reason code explaining why the label was completed.",
        examples=["remaining_spacing_repair"],
    )
    source_cells: list[str] = Field(
        default_factory=list,
        description="Original row cells used as evidence for label completion.",
        examples=[["Property, plant a nd equipment"]],
    )
    completion_source: str = Field(
        ...,
        min_length=1,
        description="Source of the completion signal.",
        examples=["spacing_repair"],
    )
    metric_values_affected: int = Field(
        ...,
        ge=0,
        description="Number of MetricValues generated from this completed row.",
        examples=[2],
    )


class NoteRowFilteringDiagnostic(BaseModel):
    """Trace of a non-metric note row filtered before MetricValue creation."""

    model_config = ConfigDict(extra="forbid")

    source_report_year: int = Field(
        ...,
        ge=1900,
        description="Annual report year from which the row was extracted.",
        examples=[2025],
    )
    page_number: int = Field(
        ...,
        gt=0,
        description="One-based PDF page number where the row was extracted.",
        examples=[225],
    )
    table_index: int = Field(
        ...,
        ge=0,
        description="Zero-based table index on the source page.",
        examples=[0],
    )
    table_type: str = Field(
        ...,
        min_length=1,
        description="Financial table category where the row originated.",
        examples=["notes"],
    )
    row_index: int = Field(
        ...,
        ge=0,
        description="Zero-based row index containing the filtered label.",
        examples=[3],
    )
    label: str = Field(
        ...,
        min_length=1,
        description="Final reconstructed/deglued label that was filtered.",
        examples=["(PKR in '000)"],
    )
    filtering_reason: str = Field(
        ...,
        min_length=1,
        description="Stable reason code explaining why the row was filtered.",
        examples=["unit_row"],
    )
    metric_values_removed: int = Field(
        ...,
        ge=0,
        description="Number of MetricValues prevented from being created.",
        examples=[2],
    )


class NoteContextInheritanceDiagnostic(BaseModel):
    """Trace of a note-table metric label enriched from active note context."""

    model_config = ConfigDict(extra="forbid")

    source_report_year: int = Field(
        ...,
        ge=1900,
        description="Annual report year from which the row was extracted.",
        examples=[2025],
    )
    page_number: int = Field(
        ...,
        gt=0,
        description="One-based PDF page number where the row was extracted.",
        examples=[321],
    )
    table_index: int = Field(
        ...,
        ge=0,
        description="Zero-based table index on the source page.",
        examples=[0],
    )
    table_type: str = Field(
        ...,
        min_length=1,
        description="Financial table category where the row originated.",
        examples=["notes"],
    )
    row_index: int = Field(
        ...,
        ge=0,
        description="Zero-based row index containing the inherited label.",
        examples=[7],
    )
    original_label: str = Field(
        ...,
        min_length=1,
        description="Label after reconstruction and degluing, before context inheritance.",
        examples=["Opening balance"],
    )
    inherited_label: str = Field(
        ...,
        min_length=1,
        description="Metric label after inheriting active note context.",
        examples=["Capital work-in-progress - Opening balance"],
    )
    inherited_context: str = Field(
        ...,
        min_length=1,
        description="Context label applied to the metric row.",
        examples=["Capital work-in-progress"],
    )
    context_source: str = Field(
        ...,
        min_length=1,
        description="Context stack source used for inheritance.",
        examples=["section_header"],
    )
    reconstruction_reason: str = Field(
        ...,
        min_length=1,
        description="Stable reason code explaining why context was inherited.",
        examples=["generic_note_label"],
    )
    metric_values_affected: int = Field(
        ...,
        ge=0,
        description="Number of MetricValues generated from this inherited row.",
        examples=[2],
    )


class HeaderInheritanceDiagnostic(BaseModel):
    """Trace of a fragmented metric label enriched from table header context."""

    model_config = ConfigDict(extra="forbid")

    source_report_year: int = Field(
        ...,
        ge=1900,
        description="Annual report year from which the row was extracted.",
        examples=[2025],
    )
    page_number: int = Field(
        ...,
        gt=0,
        description="One-based PDF page number where the row was extracted.",
        examples=[321],
    )
    table_index: int = Field(
        ...,
        ge=0,
        description="Zero-based table index on the source page.",
        examples=[0],
    )
    table_type: str = Field(
        ...,
        min_length=1,
        description="Financial table category where the row originated.",
        examples=["investment_valuation_ratios"],
    )
    row_index: int = Field(
        ...,
        ge=0,
        description="Zero-based row index containing the inherited label.",
        examples=[18],
    )
    original_label: str = Field(
        ...,
        min_length=1,
        description="Label after reconstruction/degluing before header inheritance.",
        examples=["Net assets (100"],
    )
    inherited_label: str = Field(
        ...,
        min_length=1,
        description="Metric label after table/header/unit context inheritance.",
        examples=["Net assets (100%)"],
    )
    inherited_header: str = Field(
        ...,
        min_length=1,
        description="Header, section, or unit context applied to the label.",
        examples=["%)"],
    )
    inheritance_source: str = Field(
        ...,
        min_length=1,
        description="Source of inherited context.",
        examples=["unit_context"],
    )
    reconstruction_reason: str = Field(
        ...,
        min_length=1,
        description="Stable reason code explaining why header context was inherited.",
        examples=["unit_fragment_completion"],
    )
    metric_values_affected: int = Field(
        ...,
        ge=0,
        description="Number of MetricValues generated from this inherited row.",
        examples=[2],
    )


class ExtractionQualityReport(BaseModel):
    """Post-extraction quality validation report."""

    model_config = ConfigDict(extra="forbid")

    tables_extracted: int = Field(
        default=0,
        ge=0,
        description="Number of extracted tables inspected by quality validation.",
        examples=[66],
    )
    tables_rejected: int = Field(
        default=0,
        ge=0,
        description=(
            "Number of tables that would be rejected by quality validation. "
            "This does not alter extraction output."
        ),
        examples=[12],
    )
    metric_values_generated: int = Field(
        default=0,
        ge=0,
        description="Number of MetricValues generated by extraction.",
        examples=[1151],
    )
    duplicate_metric_group_count: int = Field(
        default=0,
        ge=0,
        description="Number of metric/year/table groups with duplicate values.",
        examples=[5],
    )
    duplicate_metric_value_count: int = Field(
        default=0,
        ge=0,
        description="Number of extra duplicate MetricValue occurrences.",
        examples=[7],
    )
    conflicting_metric_group_count: int = Field(
        default=0,
        ge=0,
        description="Number of metric/year/table groups with conflicting values.",
        examples=[2],
    )
    missing_year_table_count: int = Field(
        default=0,
        ge=0,
        description="Number of tables without detected year columns.",
        examples=[10],
    )
    missing_label_table_count: int = Field(
        default=0,
        ge=0,
        description="Number of tables without detected metric labels.",
        examples=[4],
    )
    numeric_only_table_count: int = Field(
        default=0,
        ge=0,
        description="Number of tables containing numbers but no labels.",
        examples=[3],
    )
    unclassified_table_count: int = Field(
        default=0,
        ge=0,
        description="Number of extracted tables classified as unclassified_table.",
        examples=[6],
    )
    labels_reconstructed: int = Field(
        default=0,
        ge=0,
        description="Number of table rows whose metric label was reconstructed.",
        examples=[120],
    )
    metric_values_improved_by_label_reconstruction: int = Field(
        default=0,
        ge=0,
        description="Number of MetricValues receiving reconstructed metric labels.",
        examples=[240],
    )
    labels_deglued: int = Field(
        default=0,
        ge=0,
        description="Number of reconstructed labels cleaned by label degluing.",
        examples=[120],
    )
    metric_values_improved_by_label_degluing: int = Field(
        default=0,
        ge=0,
        description="Number of MetricValues receiving deglued metric labels.",
        examples=[240],
    )
    labels_completed: int = Field(
        default=0,
        ge=0,
        description="Number of fragmented labels completed by final cleanup.",
        examples=[120],
    )
    metric_values_improved_by_fragmentation_cleanup: int = Field(
        default=0,
        ge=0,
        description="Number of MetricValues receiving completed metric labels.",
        examples=[240],
    )
    note_rows_filtered: int = Field(
        default=0,
        ge=0,
        description="Number of non-metric note rows filtered before MetricValue creation.",
        examples=[12],
    )
    metric_values_removed_by_note_row_filtering: int = Field(
        default=0,
        ge=0,
        description="Number of MetricValues prevented by note-row filtering.",
        examples=[24],
    )
    context_inheritances_applied: int = Field(
        default=0,
        ge=0,
        description="Number of note-table rows enriched using context inheritance.",
        examples=[18],
    )
    metric_values_improved_by_context_inheritance: int = Field(
        default=0,
        ge=0,
        description="Number of MetricValues receiving inherited note context.",
        examples=[36],
    )
    header_inheritances_applied: int = Field(
        default=0,
        ge=0,
        description="Number of fragmented labels enriched from table/header context.",
        examples=[18],
    )
    metric_values_improved_by_header_inheritance: int = Field(
        default=0,
        ge=0,
        description="Number of MetricValues receiving inherited header context.",
        examples=[36],
    )
    scale_exempt_values: int = Field(
        default=0,
        ge=0,
        description=(
            "Number of MetricValues where table-level currency scaling was "
            "intentionally suppressed for non-currency units."
        ),
        examples=[12],
    )
    scale_corrections_applied: int = Field(
        default=0,
        ge=0,
        description=(
            "Number of MetricValues whose numeric value would have been "
            "corrupted by table-level currency scaling."
        ),
        examples=[12],
    )
    negative_values_recovered: int = Field(
        default=0,
        ge=0,
        description="Number of OCR-split accounting negatives recovered.",
        examples=[4],
    )
    shifted_rows_repaired: int = Field(
        default=0,
        ge=0,
        description="Number of rows whose values were conservatively realigned.",
        examples=[3],
    )
    values_recovered: int = Field(
        default=0,
        ge=0,
        description="Number of MetricValues recovered by row-alignment repair.",
        examples=[6],
    )
    confidence_distribution: dict[str, int] = Field(
        default_factory=dict,
        description="Distribution of table quality scores by score bucket.",
        examples=[{"0-20": 4, "20-40": 8, "40-60": 12, "60-80": 20, "80-100": 22}],
    )
    top_suspicious_tables: list[SuspiciousTableFinding] = Field(
        default_factory=list,
        description="Top table-level findings ordered by suspicion score.",
    )
    top_suspicious_metrics: list[SuspiciousMetricFinding] = Field(
        default_factory=list,
        description="Top metric-level findings ordered by suspicion score.",
    )
    label_reconstruction_diagnostics: list[LabelReconstructionDiagnostic] = Field(
        default_factory=list,
        description="Rows where metric labels were reconstructed from adjacent cells.",
    )
    label_degluing_diagnostics: list[LabelDegluingDiagnostic] = Field(
        default_factory=list,
        description="Rows where reconstructed labels were cleaned for split words.",
    )
    fragmentation_cleanup_diagnostics: list[
        FragmentationCleanupDiagnostic
    ] = Field(
        default_factory=list,
        description="Rows where fragmented labels were completed before MetricValues.",
    )
    note_row_filtering_diagnostics: list[NoteRowFilteringDiagnostic] = Field(
        default_factory=list,
        description="Rows filtered because they are note metadata, units, or markers.",
    )
    note_context_inheritance_diagnostics: list[
        NoteContextInheritanceDiagnostic
    ] = Field(
        default_factory=list,
        description="Rows whose note-table labels were enriched from context.",
    )
    header_inheritance_diagnostics: list[HeaderInheritanceDiagnostic] = Field(
        default_factory=list,
        description="Rows whose fragmented labels inherited header or unit context.",
    )


class ExtractionSummary(BaseModel):
    """Aggregated extraction linkage diagnostics for one report."""

    model_config = ConfigDict(extra="forbid")

    total_detected_tables: int = Field(
        default=0,
        ge=0,
        description="Total tables reported by the detection layer.",
        examples=[7],
    )
    total_classified_tables: int = Field(
        default=0,
        ge=0,
        description="Total table types returned by classification.",
        examples=[7],
    )
    total_extracted_tables: int = Field(
        default=0,
        ge=0,
        description="Total raw tables extracted by Camelot/pdfplumber.",
        examples=[6],
    )
    total_matched_tables: int = Field(
        default=0,
        ge=0,
        description="Total extracted tables matched to classified table types.",
        examples=[5],
    )
    unmatched_classifications: list[str] = Field(
        default_factory=list,
        description="Flattened page/table-type labels that were not matched.",
        examples=[["page=20 table_type=income_statement"]],
    )
    unmatched_extractions: list[str] = Field(
        default_factory=list,
        description="Flattened page/table-index labels that were not matched.",
        examples=[["page=20 table_index=1"]],
    )
    page_diagnostics: list[PageExtractionDiagnostic] = Field(
        default_factory=list,
        description="Detailed per-page extraction linkage diagnostics.",
    )
    tables_split: int = Field(
        default=0,
        ge=0,
        description="Total additional logical tables created by scoped splitting.",
        examples=[4],
    )
    split_reasons: list[str] = Field(
        default_factory=list,
        description="Unique reason codes for scoped table splitting.",
        examples=[["analysis_section_markers_with_repeated_year_headers"]],
    )
    logical_types_created: list[str] = Field(
        default_factory=list,
        description="Logical table types created by scoped table splitting.",
        examples=[["balance_sheet", "vertical_analysis", "horizontal_analysis"]],
    )
    id_matches: int = Field(
        default=0,
        ge=0,
        description="Total matches made by detected_table_id equality.",
        examples=[4],
    )
    bbox_matches: int = Field(
        default=0,
        ge=0,
        description="Total matches made by bounding-box IoU or containment.",
        examples=[2],
    )
    order_matches: int = Field(
        default=0,
        ge=0,
        description="Total matches made by page-level extraction order.",
        examples=[3],
    )
    fallback_matches: int = Field(
        default=0,
        ge=0,
        description="Total matches made by text-similarity fallback.",
        examples=[5],
    )
    previously_unclassified_tables_recovered: int = Field(
        default=0,
        ge=0,
        description="Total tables recovered before text-similarity fallback.",
        examples=[3],
    )
    metric_values_recovered: int = Field(
        default=0,
        ge=0,
        description="Total MetricValues carried by recovered table assignments.",
        examples=[72],
    )
    quality_report: ExtractionQualityReport = Field(
        default_factory=ExtractionQualityReport,
        description="Post-extraction quality validation report.",
    )


class ExtractedTable(BaseModel):
    """Table data extracted from a financial table on a PDF page.

    Raw rows are retained for OCR traceability. ``metric_values`` is the
    structured extraction contract: each value records the value year and the
    source report year separately.
    """

    model_config = ConfigDict(
        extra="forbid",
        populate_by_name=True,
        json_schema_extra={
            "examples": [
                {
                    "source_report_year": 2025,
                    "page_number": 20,
                    "table_type": "balance_sheet",
                    "table_index": 0,
                    "source_table_index": 0,
                    "split_table_index": None,
                    "split_reason": None,
                    "rows": [
                        ["Cash", "1000"],
                        ["Inventory", "500"],
                    ],
                    "metric_values": [
                        {
                            "metric": "Cash",
                            "value_year": 2024,
                            "value": 1000,
                            "source_report_year": 2025,
                            "page_number": 20,
                            "table_type": "balance_sheet",
                        }
                    ],
                    "extraction_summary": {
                        "total_detected_tables": 1,
                        "total_classified_tables": 1,
                        "total_extracted_tables": 1,
                        "total_matched_tables": 1,
                        "unmatched_classifications": [],
                        "unmatched_extractions": [],
                        "page_diagnostics": [
                            {
                                "source_report_year": 2025,
                                "page_number": 20,
                                "detected_table_count": 1,
                                "classified_table_count": 1,
                                "extracted_table_count": 1,
                                "matched_table_count": 1,
                                "unmatched_classifications": [],
                                "unmatched_extractions": [],
                            }
                        ],
                    },
                }
            ]
        },
    )

    source_report_year: int = Field(
        ...,
        ge=1900,
        validation_alias=AliasChoices("source_report_year", "year"),
        description="Annual report year from which this table was extracted.",
        examples=[2025],
    )
    page_number: int = Field(
        ...,
        gt=0,
        description="One-based PDF page number where the table was extracted.",
        examples=[20],
    )
    table_type: str = Field(
        ...,
        description="Financial table category assigned by the classification layer.",
        examples=["balance_sheet"],
    )
    table_index: int = Field(
        ...,
        ge=0,
        description="Zero-based table index on the source PDF page.",
        examples=[0],
    )
    source_table_index: int = Field(
        default=0,
        ge=0,
        description=(
            "Zero-based physical table index before any scoped logical splitting."
        ),
        examples=[0],
    )
    split_table_index: int | None = Field(
        default=None,
        ge=0,
        description=(
            "Zero-based logical split index within the source table, when scoped "
            "table splitting created this table."
        ),
        examples=[1],
    )
    split_reason: str | None = Field(
        default=None,
        description="Reason code for scoped logical table splitting.",
        examples=["analysis_section_markers_with_repeated_year_headers"],
    )
    detected_table_id: str | None = Field(
        default=None,
        description="Detected table identity propagated from detection/classification.",
        examples=["2025:20:0"],
    )
    page_table_index: int | None = Field(
        default=None,
        ge=0,
        description="Zero-based table index on the source page from detection order.",
        examples=[0],
    )
    bbox: BBox | None = Field(
        default=None,
        min_length=4,
        max_length=4,
        description="Detected table bounding box as [x0, y0, x1, y1].",
        examples=[[72.0, 144.0, 540.0, 320.0]],
    )
    detection_confidence: float | None = Field(
        default=None,
        ge=0,
        le=1,
        description="Detector confidence propagated with the table.",
        examples=[0.97],
    )
    match_method: str | None = Field(
        default=None,
        description="Matching strategy used to assign table_type to this extraction.",
        examples=["detected_table_id"],
    )
    rows: list[list[str]] = Field(
        default_factory=list,
        description="Raw extracted table rows retained for OCR traceability.",
        examples=[
            [
                ["Cash", "1000"],
                ["Inventory", "500"],
            ]
        ],
    )
    metric_values: list[MetricValue] = Field(
        default_factory=list,
        description=(
            "Metric/value pairs extracted from the table with value year and "
            "source report year separated."
        ),
    )

    @property
    def year(self) -> int:
        """Backward-compatible alias for source_report_year."""

        return self.source_report_year


class TableExtractionResult(BaseModel):
    """Collection of tables extracted by the OCR Table Extraction Layer."""

    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={
            "examples": [
                {
                    "tables": [
                        {
                            "source_report_year": 2025,
                            "page_number": 20,
                            "table_type": "balance_sheet",
                            "table_index": 0,
                            "rows": [
                                ["Cash", "1000"],
                                ["Inventory", "500"],
                            ],
                            "metric_values": [
                                {
                                    "metric": "Cash",
                                    "value_year": 2024,
                                    "value": 1000,
                                    "source_report_year": 2025,
                                    "page_number": 20,
                                    "table_type": "balance_sheet",
                                }
                            ],
                        }
                    ],
                    "metric_values": [
                        {
                            "metric": "Cash",
                            "value_year": 2024,
                            "value": 1000,
                            "source_report_year": 2025,
                            "page_number": 20,
                            "table_type": "balance_sheet",
                        }
                    ],
                }
            ]
        },
    )

    tables: list[ExtractedTable] = Field(
        ...,
        description="Raw financial table data returned by the extraction layer.",
    )
    metric_values: list[MetricValue] = Field(
        default_factory=list,
        description="All extracted metric values across tables in this result.",
    )
    extraction_summary: ExtractionSummary = Field(
        default_factory=ExtractionSummary,
        description="Detection/classification/extraction linkage summary.",
    )
