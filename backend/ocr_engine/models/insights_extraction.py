"""Models for OCR insights extraction results."""

from pydantic import BaseModel, ConfigDict, Field


class SectionIdentificationPageDiagnostic(BaseModel):
    """Per-page diagnostics from narrative section identification."""

    model_config = ConfigDict(extra="forbid")

    page_number: int = Field(
        ...,
        gt=0,
        description="One-based PDF page number inspected for narrative sections.",
        examples=[84],
    )
    text_source: str = Field(
        ...,
        min_length=1,
        description="Text source selected for the page.",
        examples=["pymupdf", "ocr", "none"],
    )
    pymupdf: bool = Field(
        ...,
        description="Whether PyMuPDF extracted usable text for the page.",
        examples=[True],
    )
    ocr: bool = Field(
        ...,
        description="Whether OCR extracted usable fallback text for the page.",
        examples=[False],
    )
    page_type: str = Field(
        ...,
        min_length=1,
        description="Heuristic page type assigned before section selection.",
        examples=["narrative", "notes", "auditor_report"],
    )
    detected_section: str | None = Field(
        default=None,
        description="Accepted narrative section, if the page passed scoring.",
        examples=["Business Review"],
    )
    confidence_score: float = Field(
        ...,
        ge=0,
        le=1,
        description="Section-identification confidence score from 0 to 1.",
        examples=[0.86],
    )
    rejection_reason: str | None = Field(
        default=None,
        description="Reason the page was not accepted as narrative.",
        examples=["page_type_notes"],
    )
    heading_match: bool = Field(
        default=False,
        description="Whether a section alias matched the page heading area.",
        examples=[True],
    )
    section_alias_match: bool = Field(
        default=False,
        description="Whether a known section alias matched the page.",
        examples=[True],
    )
    is_continuation: bool = Field(
        default=False,
        description="Whether this page inherited its section from a prior page.",
        examples=[True],
    )
    continuation_index: int = Field(
        default=0,
        ge=0,
        description=(
            "One-based continuation count since the latest direct section heading; "
            "zero when the page is not a continuation."
        ),
        examples=[2],
    )
    continuation_budget_exceeded: bool = Field(
        default=False,
        description="Whether this page exceeded the configured continuation budget.",
        examples=[False],
    )
    narrative_density: float = Field(
        default=0.0,
        ge=0,
        le=1,
        description="Estimated proportion of prose-like lines on the page.",
        examples=[0.72],
    )
    table_density: float = Field(
        default=0.0,
        ge=0,
        le=1,
        description="Estimated proportion of table-like lines on the page.",
        examples=[0.18],
    )
    ignored_keyword_count: int = Field(
        default=0,
        ge=0,
        description="Number of ignored-page keyword signals in the heading area.",
        examples=[0],
    )
    ocr_engine_selected: str | None = Field(
        default=None,
        description="OCR engine selected for the page when OCR text was used.",
        examples=["tesseract_ocr"],
    )
    pymupdf_ocr_confidence: float | None = Field(
        default=None,
        ge=0,
        le=1,
        description="Section-classifier confidence for PyMuPDF OCR text.",
        examples=[0.42],
    )
    tesseract_ocr_confidence: float | None = Field(
        default=None,
        ge=0,
        le=1,
        description="Section-classifier confidence for direct Tesseract OCR text.",
        examples=[0.91],
    )
    ocr_escalation_reason: str | None = Field(
        default=None,
        description="Reason PyMuPDF OCR was escalated to direct Tesseract OCR.",
        examples=["classifier_confidence_below_threshold,weak_heading_alias_match"],
    )
    ocr_escalated: bool = Field(
        default=False,
        description="Whether direct Tesseract OCR was attempted after PyMuPDF OCR.",
        examples=[True],
    )
    ocr_recovered: bool = Field(
        default=False,
        description=(
            "Whether escalation selected Tesseract text that passed section "
            "classification where PyMuPDF OCR did not."
        ),
        examples=[True],
    )
    ocr_heading_alias_match_count: int = Field(
        default=0,
        ge=0,
        description="Number of known section aliases matched in the selected OCR heading.",
        examples=[1],
    )
    ocr_heading_fragmentation_ratio: float = Field(
        default=0.0,
        ge=0,
        le=1,
        description="Estimated heading fragmentation ratio for selected OCR text.",
        examples=[0.12],
    )
    ocr_single_character_line_count: int = Field(
        default=0,
        ge=0,
        description="Count of one-character OCR fragments in selected heading lines.",
        examples=[0],
    )


class SectionIdentificationReport(BaseModel):
    """Diagnostics report for narrative section identification."""

    model_config = ConfigDict(extra="forbid")

    total_pages: int = Field(
        default=0,
        ge=0,
        description="Number of pages inspected by the section identifier.",
    )
    pages_with_pymupdf_text: int = Field(
        default=0,
        ge=0,
        description="Number of pages with usable PyMuPDF text.",
    )
    pages_with_ocr_text: int = Field(
        default=0,
        ge=0,
        description="Number of pages with usable OCR fallback text.",
    )
    accepted_pages: int = Field(
        default=0,
        ge=0,
        description="Number of pages accepted as narrative section pages.",
    )
    rejected_pages: int = Field(
        default=0,
        ge=0,
        description="Number of pages rejected from narrative section extraction.",
    )
    page_type_counts: dict[str, int] = Field(
        default_factory=dict,
        description="Page count by heuristic page type.",
    )
    text_source_counts: dict[str, int] = Field(
        default_factory=dict,
        description="Page count by selected text source.",
    )
    ocr_engine_counts: dict[str, int] = Field(
        default_factory=dict,
        description="OCR page count by selected OCR engine.",
    )
    ocr_pages_escalated: int = Field(
        default=0,
        ge=0,
        description="Number of pages escalated from PyMuPDF OCR to Tesseract OCR.",
    )
    ocr_pages_recovered: int = Field(
        default=0,
        ge=0,
        description="Number of pages recovered by selecting Tesseract OCR output.",
    )
    additional_accepted_pages: int = Field(
        default=0,
        ge=0,
        description=(
            "Estimated pages accepted because Tesseract OCR beat rejected "
            "PyMuPDF OCR output."
        ),
    )
    continuation_resets: int = Field(
        default=0,
        ge=0,
        description=(
            "Number of pages rejected because inherited section continuation "
            "exceeded the configured budget."
        ),
    )
    continuation_budget_exceeded: int = Field(
        default=0,
        ge=0,
        description=(
            "Number of inspected pages whose inherited section continuation "
            "exceeded the configured budget."
        ),
    )
    page_diagnostics: list[SectionIdentificationPageDiagnostic] = Field(
        default_factory=list,
        description="Per-page section-identification diagnostics.",
    )


class Insight(BaseModel):
    """Business insight extracted from narrative annual-report text.

    ``value_year`` is the year the insight discusses. ``source_report_year`` is
    the annual report where the narrative was found.
    """

    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={
            "examples": [
                {
                    "value_year": 2024,
                    "source_report_year": 2025,
                    "area": "Debt",
                    "takeaway": "Borrowings increased to finance expansion.",
                    "source_section": "Management Discussion & Analysis",
                    "page_number": 84,
                    "confidence": 0.93,
                }
            ]
        },
    )

    value_year: int = Field(
        ...,
        ge=1900,
        description="Financial year discussed by the insight.",
        examples=[2024],
    )
    source_report_year: int = Field(
        ...,
        ge=1900,
        description="Annual report year from which the insight originated.",
        examples=[2025],
    )
    area: str = Field(
        ...,
        min_length=1,
        description="Business topic or theme associated with the extracted insight.",
        examples=["Debt", "Geographic Expansion"],
    )
    takeaway: str = Field(
        ...,
        min_length=1,
        description="Concise extracted business insight from the report text.",
        examples=["Borrowings increased to finance expansion."],
    )
    source_section: str = Field(
        ...,
        min_length=1,
        description="Annual-report section where the insight was found.",
        examples=["Management Discussion & Analysis"],
    )
    page_number: int = Field(
        ...,
        gt=0,
        description="One-based PDF page number where the source narrative appears.",
        examples=[84],
    )
    confidence: float = Field(
        ...,
        ge=0,
        le=1,
        description="Confidence score for the extracted insight.",
        examples=[0.93],
    )


class InsightsExtractionDiagnostics(BaseModel):
    """Operational diagnostics for the annual-report insights extraction flow."""

    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={
            "examples": [
                {
                    "total_pages_processed": 400,
                    "pages_with_text": 312,
                    "total_text_characters": 745000,
                    "section_pages": 84,
                    "total_chunks_created": 126,
                    "chunk_size": 2800,
                    "chunk_overlap": 250,
                    "retrieval_strategy": (
                        "section_balanced_score_all_relevant_chunks"
                    ),
                    "top_k": None,
                    "chunks_sent_to_llm": 96,
                    "llm_call_count": 12,
                    "generated_insights": 54,
                    "section_page_count_by_section": {
                        "Business Review": 28,
                        "Risks": 14,
                    },
                    "chunk_count_by_section": {
                        "Business Review": 42,
                        "Risks": 18,
                    },
                    "ranked_chunk_count_by_section": {
                        "Business Review": 42,
                        "Risks": 18,
                    },
                    "insight_count_by_section": {
                        "Business Review": 29,
                        "Risks": 8,
                    },
                    "rejected_low_confidence_count": 4,
                    "review_bucket_count": 7,
                    "exported_high_confidence_count": 43,
                    "generic_filtered_count": 3,
                    "confidence_distribution": {
                        "0.0": 1,
                        "0.1-0.5": 3,
                        "0.5-0.7": 7,
                        "0.7-0.9": 37,
                        "0.9+": 6,
                    },
                    "section_identification_report": {
                        "total_pages": 400,
                        "pages_with_pymupdf_text": 312,
                        "pages_with_ocr_text": 34,
                        "accepted_pages": 84,
                        "rejected_pages": 316,
                        "page_type_counts": {"narrative": 84},
                        "text_source_counts": {"pymupdf": 312, "ocr": 34},
                        "ocr_engine_counts": {"tesseract_ocr": 12},
                        "ocr_pages_escalated": 18,
                        "ocr_pages_recovered": 9,
                        "additional_accepted_pages": 9,
                        "page_diagnostics": [],
                    },
                }
            ]
        },
    )

    total_pages_processed: int = Field(
        default=0,
        ge=0,
        description="Total PDF pages inspected during narrative text extraction.",
    )
    pages_with_text: int = Field(
        default=0,
        ge=0,
        description="Number of pages with extractable narrative text.",
    )
    total_text_characters: int = Field(
        default=0,
        ge=0,
        description="Total extracted text length in characters.",
    )
    section_pages: int = Field(
        default=0,
        ge=0,
        description="Number of extracted pages assigned to relevant narrative sections.",
    )
    total_chunks_created: int = Field(
        default=0,
        ge=0,
        description="Number of narrative chunks created before ranking.",
    )
    chunk_size: int = Field(
        default=0,
        ge=0,
        description="Configured maximum characters per narrative chunk.",
    )
    chunk_overlap: int = Field(
        default=0,
        ge=0,
        description="Configured overlapping characters between split chunks.",
    )
    retrieval_strategy: str = Field(
        default="section_balanced_score_all_relevant_chunks",
        min_length=1,
        description="Chunk retrieval and ranking strategy used before LLM analysis.",
    )
    top_k: int | None = Field(
        default=None,
        ge=1,
        description=(
            "Optional ranked chunk limit. Null means all relevant chunks were used."
        ),
    )
    chunks_sent_to_llm: int = Field(
        default=0,
        ge=0,
        description="Number of ranked chunks included across LLM requests.",
    )
    llm_call_count: int = Field(
        default=0,
        ge=0,
        description="Number of LLM requests used for the report.",
    )
    generated_insights: int = Field(
        default=0,
        ge=0,
        description="Number of validated and deduplicated insights returned.",
    )
    section_page_count_by_section: dict[str, int] = Field(
        default_factory=dict,
        description="Relevant narrative page count by source section.",
    )
    chunk_count_by_section: dict[str, int] = Field(
        default_factory=dict,
        description="Created chunk count by source section before ranking.",
    )
    ranked_chunk_count_by_section: dict[str, int] = Field(
        default_factory=dict,
        description="Ranked chunk count by source section sent to the LLM.",
    )
    insight_count_by_section: dict[str, int] = Field(
        default_factory=dict,
        description="Generated insight count by source section.",
    )
    rejected_low_confidence_count: int = Field(
        default=0,
        ge=0,
        description="Number of insights rejected from workbook output.",
    )
    review_bucket_count: int = Field(
        default=0,
        ge=0,
        description="Number of insights routed to the Insights Review worksheet.",
    )
    exported_high_confidence_count: int = Field(
        default=0,
        ge=0,
        description="Number of insights routed to the main Insights worksheet.",
    )
    generic_filtered_count: int = Field(
        default=0,
        ge=0,
        description="Number of generic low-confidence insights filtered out.",
    )
    confidence_distribution: dict[str, int] = Field(
        default_factory=dict,
        description="Insight count by confidence bucket.",
    )
    section_identification_report: SectionIdentificationReport = Field(
        default_factory=SectionIdentificationReport,
        description="Page-level diagnostics from section identification.",
    )


class InsightsExtractionResult(BaseModel):
    """Collection of business insights extracted from annual-report text."""

    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={
            "examples": [
                {
                    "insights": [
                        {
                            "value_year": 2024,
                            "source_report_year": 2025,
                            "area": "Debt",
                            "takeaway": "Borrowings increased to finance expansion.",
                            "source_section": "Management Discussion & Analysis",
                            "page_number": 84,
                            "confidence": 0.93,
                        },
                        {
                            "value_year": 2025,
                            "source_report_year": 2025,
                            "area": "Exports",
                            "takeaway": (
                                "Export sales increased due to Middle East "
                                "expansion."
                            ),
                            "source_section": "Business Review",
                            "page_number": 92,
                            "confidence": 0.9,
                        },
                    ],
                    "diagnostics": {
                        "total_pages_processed": 400,
                        "pages_with_text": 312,
                        "total_text_characters": 745000,
                        "section_pages": 84,
                        "total_chunks_created": 126,
                        "chunk_size": 2800,
                        "chunk_overlap": 250,
                        "retrieval_strategy": (
                            "section_balanced_score_all_relevant_chunks"
                        ),
                        "top_k": None,
                        "chunks_sent_to_llm": 96,
                        "llm_call_count": 12,
                        "generated_insights": 54,
                        "section_page_count_by_section": {
                            "Business Review": 28
                        },
                        "chunk_count_by_section": {"Business Review": 42},
                        "ranked_chunk_count_by_section": {"Business Review": 42},
                        "insight_count_by_section": {"Business Review": 29},
                    },
                }
            ]
        },
    )

    insights: list[Insight] = Field(
        ...,
        description="Business insights extracted from narrative annual-report sections.",
    )
    diagnostics: InsightsExtractionDiagnostics = Field(
        default_factory=InsightsExtractionDiagnostics,
        description="Trace diagnostics for the insights extraction run.",
    )
