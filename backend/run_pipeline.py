"""CLI entry point for running the OCR pipeline."""

from __future__ import annotations

import argparse
import json
import logging
import os
import re
from pathlib import Path

from ocr_engine.pipeline.factory import build_ocr_pipeline
from ocr_engine.pipeline.interfaces.ocr_pipeline import IOCRPipeline
from shared.config.settings import ConfigurationValidator, Settings, get_settings
from shared.models.company_context import CompanyContext
from shared.models.report import Report


def build_default_pipeline(
    settings: Settings | None = None,
    *,
    output_xlsx: str | Path | None = None,
) -> IOCRPipeline:
    """Build the production OCR pipeline using the default service implementations."""

    return build_ocr_pipeline(settings or get_settings(), output_xlsx=output_xlsx)


def build_context_from_pdf(
    *,
    pdf_path: str | Path,
    report_year: int | None = None,
    company_name: str | None = None,
    template_xlsx: str | Path | None = None,
) -> CompanyContext:
    """Build a single-report company context from a PDF path."""

    resolved_pdf_path = Path(pdf_path).expanduser().resolve()
    if not resolved_pdf_path.is_file():
        raise FileNotFoundError(f"PDF file does not exist: {resolved_pdf_path}")

    inferred_year = report_year or _infer_report_year(resolved_pdf_path)
    resolved_company_name = company_name or _infer_company_name(resolved_pdf_path)
    report_id = f"rpt_{inferred_year}_{_slugify(resolved_pdf_path.stem)}"

    return CompanyContext(
        company_name=resolved_company_name,
        reports=[
            Report(
                id=report_id,
                company_name=resolved_company_name,
                year=inferred_year,
                file_name=resolved_pdf_path.name,
                file_path=str(resolved_pdf_path),
            )
        ],
        workbook_template_path=(
            str(Path(template_xlsx).expanduser().resolve()) if template_xlsx else None
        ),
    )


def main() -> None:
    """Run OCR from a PDF path or a serialized CompanyContext JSON file."""

    parser = argparse.ArgumentParser(description="Run the OCR pipeline.")
    parser.add_argument(
        "--context-json",
        default=os.getenv("OCR_CONTEXT_JSON"),
        help="Path to a CompanyContext JSON input file.",
    )
    parser.add_argument(
        "--pdf-path",
        default=os.getenv("OCR_PDF_PATH"),
        help=(
            "Path to an annual-report PDF. Used as a simpler alternative "
            "to --context-json."
        ),
    )
    parser.add_argument(
        "--output-xlsx",
        default=os.getenv("OCR_OUTPUT_XLSX"),
        help="Path where the generated mapped workbook should be written.",
    )
    parser.add_argument(
        "--template-xlsx",
        default=os.getenv("OCR_TEMPLATE_XLSX"),
        help="Optional accountant-built Excel template to populate.",
    )
    parser.add_argument(
        "--company-name",
        default=os.getenv("OCR_COMPANY_NAME"),
        help=(
            "Company name for --pdf-path mode. Defaults to a cleaned PDF "
            "filename."
        ),
    )
    parser.add_argument(
        "--report-year",
        type=int,
        default=_env_int("OCR_REPORT_YEAR"),
        help=(
            "Report year for --pdf-path mode. Defaults to the last year found "
            "in the PDF filename."
        ),
    )
    parser.add_argument(
        "--output-json",
        default=os.getenv("OCR_OUTPUT_JSON"),
        help="Optional path for the populated CompanyContext JSON output.",
    )
    args = parser.parse_args()

    if bool(args.context_json) == bool(args.pdf_path):
        parser.error("provide exactly one of --pdf-path or --context-json.")

    logging.basicConfig(level=logging.INFO)
    settings = get_settings()
    ConfigurationValidator(settings).validate_startup()

    if args.pdf_path:
        try:
            context = build_context_from_pdf(
                pdf_path=args.pdf_path,
                report_year=args.report_year,
                company_name=args.company_name,
                template_xlsx=args.template_xlsx,
            )
        except (FileNotFoundError, ValueError) as exc:
            parser.error(str(exc))
    else:
        input_path = Path(args.context_json)
        context = CompanyContext.model_validate_json(
            input_path.read_text(encoding="utf-8")
        )

    result = build_default_pipeline(settings, output_xlsx=args.output_xlsx).process(
        context
    )
    output_text = json.dumps(result.model_dump(mode="json"), indent=2)

    if args.output_json:
        output_path = Path(args.output_json)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(output_text, encoding="utf-8")
    elif not args.pdf_path:
        print(output_text)

    if args.pdf_path:
        if result.pipeline_errors:
            formatted_errors = "; ".join(
                f"{error.layer_name}: {error.error_message}"
                for error in result.pipeline_errors
            )
            raise SystemExit(f"Pipeline failed: {formatted_errors}")
        if result.generated_workbook is None:
            raise SystemExit("Pipeline did not generate a workbook.")
        print(result.generated_workbook.output_file_path)


def _infer_report_year(pdf_path: Path) -> int:
    """Infer the reporting year from the PDF filename."""

    year_matches = re.findall(r"(?:19|20)\d{2}", pdf_path.stem)
    if not year_matches:
        raise ValueError(
            "--report-year is required when the PDF filename does not contain a year."
        )
    return int(year_matches[-1])


def _infer_company_name(pdf_path: Path) -> str:
    """Infer a readable company name from the PDF filename."""

    without_years = re.sub(r"(?:19|20)\d{2}", " ", pdf_path.stem)
    normalized = re.sub(r"[_\-.]+", " ", without_years)
    normalized = re.sub(
        r"\b(annual|report|financial|statements?|accounts?)\b",
        " ",
        normalized,
        flags=re.IGNORECASE,
    )
    company_name = " ".join(normalized.split())
    return company_name or pdf_path.stem


def _slugify(value: str) -> str:
    """Convert a filename stem into a stable report identifier suffix."""

    slug = re.sub(r"[^a-zA-Z0-9]+", "_", value).strip("_").lower()
    return slug or "annual_report"


def _env_int(name: str) -> int | None:
    """Read an optional integer environment variable."""

    raw_value = os.getenv(name)
    if raw_value is None or not raw_value.strip():
        return None
    return int(raw_value)


if __name__ == "__main__":
    main()
