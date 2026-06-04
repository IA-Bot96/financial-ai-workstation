"""OCR V2 Bridge Phase B1 raw table ingestion.

This module consumes existing bbox extraction CSV artifacts and explodes them
into raw extracted table cells. It does not perform candidate capture,
governance, selection, ranking, scoring, workbook generation, OCR-to-MSIL
export, or LLM behavior.
"""

from __future__ import annotations

import csv
import json
import os
import re
from pathlib import Path
from typing import Any, Iterable

from pydantic import BaseModel, ConfigDict, Field, model_validator


DEFAULT_BBOX_TABLES_DIR = Path("output/bbox_extraction_poc/tables")


class ExtractedTableDocumentContext(BaseModel):
    """Document-derived context carried alongside each extracted table cell."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    statement_title: str | None = None
    section_heading: str | None = None
    notes_to_marker: bool = False
    named_entities: tuple[str, ...] = Field(default_factory=tuple)
    units_scale_text: str | None = None
    entity_context: str | None = None


class ExtractedTableCell(BaseModel):
    """One numeric-looking cell extracted from a raw table CSV."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    raw_value: str = Field(..., min_length=1)
    raw_label: str = Field(..., min_length=1)
    value_year: int = Field(..., ge=1900)
    page_number: int = Field(..., gt=0)
    table_reference: str = Field(..., min_length=1)
    locator: str = Field(..., min_length=1)
    source_scale: str = Field(..., min_length=1)
    source_unit: str = Field(..., min_length=1)
    section_label: str | None = None
    source_file: str = Field(..., min_length=1)
    document_context: ExtractedTableDocumentContext = Field(
        default_factory=ExtractedTableDocumentContext
    )


class OCRV2RawTableIngestionResult(BaseModel):
    """Result of bridge raw-table ingestion."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    tables_processed: int = Field(..., ge=0)
    cells: tuple[ExtractedTableCell, ...] = Field(default_factory=tuple)
    candidate_rows_generated: int = Field(..., ge=0)
    table_files: tuple[str, ...] = Field(default_factory=tuple)

    @model_validator(mode="after")
    def _validate_counts(self) -> "OCRV2RawTableIngestionResult":
        if self.candidate_rows_generated != len(self.cells):
            raise ValueError("candidate_rows_generated must equal len(cells).")
        if self.tables_processed != len(self.table_files):
            raise ValueError("tables_processed must equal len(table_files).")
        return self


class OCRV2TableAdapter:
    """Ingest bbox extraction CSVs into raw extracted candidate cells."""

    def __init__(
        self,
        *,
        page_context_provider: "OCRV2PageContextProvider | None" = None,
        enable_page_context: bool = True,
    ) -> None:
        self._page_context_provider = (
            page_context_provider or OCRV2PageContextProvider()
            if enable_page_context
            else OCRV2PageContextProvider.disabled()
        )

    def ingest_directory(
        self,
        tables_dir: str | Path = DEFAULT_BBOX_TABLES_DIR,
        *,
        pattern: str = "*.csv",
    ) -> OCRV2RawTableIngestionResult:
        """Read all matching CSV table artifacts deterministically."""

        directory = Path(tables_dir)
        self._page_context_provider.prepare(directory)
        table_paths = tuple(sorted(directory.glob(pattern)))
        cells: list[ExtractedTableCell] = []
        for table_path in table_paths:
            cells.extend(self.ingest_table(table_path))
        return OCRV2RawTableIngestionResult(
            tables_processed=len(table_paths),
            cells=tuple(cells),
            candidate_rows_generated=len(cells),
            table_files=tuple(str(path) for path in table_paths),
        )

    def ingest_tables(
        self,
        table_paths: Iterable[str | Path],
    ) -> OCRV2RawTableIngestionResult:
        """Read a supplied collection of CSV table artifacts deterministically."""

        paths = tuple(sorted(Path(path) for path in table_paths))
        cells: list[ExtractedTableCell] = []
        for table_path in paths:
            cells.extend(self.ingest_table(table_path))
        return OCRV2RawTableIngestionResult(
            tables_processed=len(paths),
            cells=tuple(cells),
            candidate_rows_generated=len(cells),
            table_files=tuple(str(path) for path in paths),
        )

    def ingest_table(self, table_path: str | Path) -> tuple[ExtractedTableCell, ...]:
        """Explode one CSV table into numeric-looking cells."""

        path = Path(table_path)
        page_number = _page_number_from_filename(path.name)
        table_reference = path.stem
        rows = _read_csv_rows(path)
        normalized_rows = tuple(tuple(_clean_cell(cell) for cell in row) for row in rows)
        page_context = self._page_context_provider.context_for_page(page_number)
        statement_title = _statement_title_from_rows(normalized_rows)
        notes_to_marker = _notes_to_marker_from_rows(normalized_rows)
        named_entities = _named_entities_from_rows(normalized_rows)
        table_units_scale_text = _units_scale_text_from_rows(normalized_rows)
        cells: list[ExtractedTableCell] = []
        active_year_columns: dict[int, int] = {}
        active_section_label: str | None = None
        active_scale = "source_header:unspecified"
        active_unit = "unknown"

        for row_index, normalized_row in enumerate(normalized_rows, start=1):
            year_columns = _year_columns(normalized_row)
            scale, unit = _scale_from_row(normalized_row, year_columns)
            section_label = _section_label_from_row(normalized_row, year_columns)

            if scale:
                active_scale = scale
                active_unit = unit
            if section_label:
                active_section_label = section_label
                if _section_is_percentage_analysis(section_label):
                    active_scale = "source_header:percentage"
                    active_unit = "%"
            if year_columns:
                active_year_columns = year_columns
                continue
            if not active_year_columns:
                continue
            section_heading = _section_heading_from_row(
                normalized_row,
                active_year_columns,
            )
            if section_heading:
                active_section_label = section_heading
                if _section_is_percentage_analysis(section_heading):
                    active_scale = "source_header:percentage"
                    active_unit = "%"
                continue

            label = _label_from_row(normalized_row, min(active_year_columns))
            if not label:
                label = _label_from_unlabeled_balance_sheet_subtotal(
                    normalized_rows,
                    row_index - 1,
                    active_year_columns,
                    active_section_label,
                )
                if not label:
                    continue
            candidate_scale, candidate_unit = _scale_for_label(
                label,
                active_scale,
                active_unit,
            )
            for column_index, value_year in active_year_columns.items():
                if column_index >= len(normalized_row):
                    continue
                raw_value = normalized_row[column_index]
                if not _is_numeric_value(raw_value):
                    continue
                cells.append(
                    ExtractedTableCell(
                        raw_value=raw_value,
                        raw_label=label,
                        value_year=value_year,
                        page_number=page_number,
                        table_reference=table_reference,
                        locator=f"{path.name}:row:{row_index}:col:{column_index + 1}",
                        source_scale=candidate_scale,
                        source_unit=candidate_unit,
                        section_label=active_section_label,
                        source_file=str(path),
                        document_context=_merge_document_context(
                            page_context=page_context,
                            table_statement_title=statement_title,
                            table_notes_to_marker=notes_to_marker,
                            table_named_entities=named_entities,
                            section_heading=active_section_label,
                            units_scale_text=_units_scale_context_text(
                                candidate_scale,
                                candidate_unit,
                                table_units_scale_text,
                            ),
                        ),
                    )
                )
        return tuple(cells)


class OCRV2PageContextProvider:
    """Deterministic page-text context provider for OCR V2 bridge enrichment."""

    def __init__(
        self,
        *,
        pdf_path: str | Path | None = None,
        page_text_by_page: dict[int, str] | None = None,
        enabled: bool = True,
    ) -> None:
        self._explicit_pdf_path = Path(pdf_path) if pdf_path else None
        self._page_text_by_page = dict(page_text_by_page or {})
        self._enabled = enabled
        self._prepared_pdf_path: Path | None = None
        self._context_cache: dict[int, ExtractedTableDocumentContext] = {}

    @classmethod
    def disabled(cls) -> "OCRV2PageContextProvider":
        return cls(enabled=False)

    def prepare(self, tables_dir: Path) -> None:
        if not self._enabled:
            return
        if self._prepared_pdf_path is not None or self._page_text_by_page:
            return
        self._prepared_pdf_path = _resolve_page_context_pdf_path(tables_dir)

    def context_for_page(self, page_number: int) -> ExtractedTableDocumentContext:
        if not self._enabled:
            return ExtractedTableDocumentContext()
        if page_number not in self._context_cache:
            self._context_cache[page_number] = _context_from_page_text(
                self._page_text(page_number)
            )
        return self._context_cache[page_number]

    def _page_text(self, page_number: int) -> str:
        if page_number in self._page_text_by_page:
            return self._page_text_by_page[page_number]
        pdf_path = self._explicit_pdf_path or self._prepared_pdf_path
        if not pdf_path:
            return ""
        return _extract_pdf_page_text(pdf_path, page_number)


def _read_csv_rows(path: Path) -> tuple[tuple[str, ...], ...]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return tuple(tuple(row) for row in csv.reader(handle))


def _resolve_page_context_pdf_path(tables_dir: Path) -> Path | None:
    env_path = os.environ.get("OCR_V2_PAGE_CONTEXT_PDF")
    if env_path and Path(env_path).exists():
        return Path(env_path)

    candidate_metadata_paths = (
        tables_dir / "bbox_extraction_poc.json",
        tables_dir.parent / "bbox_extraction_poc.json",
        tables_dir.parent.parent / "bbox_extraction_poc.json",
    )
    for metadata_path in candidate_metadata_paths:
        pdf_path = _pdf_path_from_metadata(metadata_path)
        if pdf_path:
            return pdf_path

    discovered = tuple(sorted(Path("output").glob("*/bbox_extraction_poc.json")))
    if len(discovered) == 1:
        return _pdf_path_from_metadata(discovered[0])
    discovered_pdf_paths = tuple(
        path for path in (_pdf_path_from_metadata(metadata) for metadata in discovered) if path
    )
    unique_pdf_paths = tuple(dict.fromkeys(discovered_pdf_paths))
    if len(unique_pdf_paths) == 1:
        return unique_pdf_paths[0]
    return None


def _pdf_path_from_metadata(metadata_path: Path) -> Path | None:
    if not metadata_path.exists():
        return None
    try:
        payload = json.loads(metadata_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    pdf_path = payload.get("pdf_path")
    if not pdf_path:
        return None
    path = Path(pdf_path)
    return path if path.exists() else None


def _extract_pdf_page_text(pdf_path: Path, page_number: int) -> str:
    try:
        import pdfplumber
    except ImportError:
        return ""
    try:
        with pdfplumber.open(str(pdf_path)) as pdf:
            page_index = page_number - 1
            if page_index < 0 or page_index >= len(pdf.pages):
                return ""
            return pdf.pages[page_index].extract_text() or ""
    except Exception:
        return ""


def _page_number_from_filename(filename: str) -> int:
    match = re.search(r"page_(\d{4})", filename)
    if not match:
        raise ValueError(f"Cannot determine page number from filename: {filename}")
    return int(match.group(1))


def _clean_cell(value: Any) -> str:
    text = "" if value is None else str(value)
    text = text.replace("\ufeff", "")
    text = text.replace("\u2018", "'").replace("\u2019", "'")
    text = text.replace("\u2013", "-").replace("\u2014", "-")
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def _row_text(row: tuple[str, ...]) -> str:
    return re.sub(r"\s+", " ", " ".join(cell for cell in row if cell)).strip()


def _context_from_page_text(page_text: str) -> ExtractedTableDocumentContext:
    lines = _page_text_lines(page_text)
    return ExtractedTableDocumentContext(
        statement_title=_statement_title_from_page_lines(lines),
        notes_to_marker=_notes_to_marker_from_page_lines(lines),
        named_entities=_named_entities_from_text(" ".join(lines[:24])),
        entity_context=_entity_context_from_page_lines(lines),
    )


def _page_text_lines(page_text: str) -> tuple[str, ...]:
    return tuple(
        line
        for line in (_clean_cell(raw_line) for raw_line in page_text.splitlines())
        if line
    )


def _statement_title_from_page_lines(lines: tuple[str, ...]) -> str | None:
    for index, line in enumerate(lines[:14]):
        joined = _title_candidate_from_lines(lines, index)
        normalized = joined.lower()
        if not joined:
            continue
        if "notes to" in normalized and "financial statement" in normalized:
            return joined
        if _page_statement_title_like(normalized):
            return joined
    return None


def _title_candidate_from_lines(lines: tuple[str, ...], start_index: int) -> str:
    title_lines: list[str] = []
    for line in lines[start_index : start_index + 4]:
        normalized = line.lower()
        if title_lines and _line_starts_non_title_context(normalized):
            break
        if _has_explicit_scale_marker(normalized):
            break
        if re.search(r"\b(19|20)\d{2}\b", normalized):
            break
        title_lines.append(line)
        joined = " ".join(title_lines).lower()
        if _page_title_complete(joined):
            break
    return re.sub(r"\s+", " ", " ".join(title_lines)).strip()


def _line_starts_non_title_context(normalized: str) -> bool:
    return normalized.startswith(
        (
            "as at ",
            "for the year",
            "note ",
            "(pkr",
            "pkr ",
            "assets",
            "liabilities",
            "cash flows",
        )
    )


def _page_title_complete(normalized: str) -> bool:
    return (
        ("notes to" in normalized and "financial statement" in normalized)
        or "statement of financial position" in normalized
        or "statement of profit or loss" in normalized
        or "statement of comprehensive income" in normalized
        or "statement of cash flow" in normalized
        or "statement of cash flows" in normalized
        or "statement of changes in equity" in normalized
        or "financial highlights six years at a glance" in normalized
        or "analysis of statement of financial position" in normalized
        or "analysis of statement of profit or loss" in normalized
    )


def _page_statement_title_like(normalized: str) -> bool:
    return any(
        marker in normalized
        for marker in (
            "statement of",
            "analysis of statement",
            "notes to",
            "financial highlights",
            "years at a glance",
        )
    )


def _notes_to_marker_from_page_lines(lines: tuple[str, ...]) -> bool:
    text = " ".join(lines[:10]).lower()
    return "notes to" in text and "financial statement" in text


def _entity_context_from_page_lines(lines: tuple[str, ...]) -> str | None:
    for index, line in enumerate(lines[:24]):
        candidate = _entity_context_candidate(line, lines, index)
        if candidate:
            return candidate
    return None


def _entity_context_candidate(
    line: str,
    lines: tuple[str, ...],
    index: int,
) -> str | None:
    normalized = line.lower()
    if any(
        marker in normalized
        for marker in (
            "investment in associate",
            "investment in associates",
            "investment in subsidiary",
            "investment in subsidiaries",
            "joint venture",
            "associates",
            "associate",
            "subsidiary",
            "subsidiaries",
        )
    ):
        return _context_window(lines, index)
    if re.search(r"\b\d+(?:\.\d+)+\s+.+(?:limited|ltd|holdings|corporation)\b", normalized):
        return _context_window(lines, index)
    return None


def _context_window(lines: tuple[str, ...], index: int) -> str:
    start = max(index - 1, 0)
    end = min(index + 3, len(lines))
    return re.sub(r"\s+", " ", " ".join(lines[start:end])).strip()


def _statement_title_from_rows(rows: tuple[tuple[str, ...], ...]) -> str | None:
    """Return the most explicit title-like row near the top of a table."""

    for row in rows[:8]:
        year_columns = _year_columns(row)
        if year_columns:
            candidate = _section_label_from_row(row, year_columns)
        else:
            candidate = _row_text(row)
        if not candidate:
            continue
        if _looks_like_value_row(row, year_columns):
            continue
        if not re.search(r"[A-Za-z]", candidate):
            continue
        if _is_title_like_text(candidate):
            return candidate
    return None


def _is_title_like_text(value: str) -> bool:
    normalized = value.lower()
    compact = re.sub(r"\s+", " ", normalized)
    return any(
        marker in compact
        for marker in (
            "statement",
            "financial position",
            "financial performance",
            "cash flow",
            "cash flows",
            "changes in equity",
            "six year",
            "six-year",
            "summary",
            "analysis",
            "notes to",
            "note ",
        )
    )


def _notes_to_marker_from_rows(rows: tuple[tuple[str, ...], ...]) -> bool:
    text = " ".join(_row_text(row).lower() for row in rows[:12])
    return "notes to" in text and "financial statement" in text


def _named_entities_from_rows(rows: tuple[tuple[str, ...], ...]) -> tuple[str, ...]:
    """Extract deterministic acronym-style entity hints when available."""

    text = " ".join(_row_text(row) for row in rows[:16])
    return _named_entities_from_text(text)


def _named_entities_from_text(text: str) -> tuple[str, ...]:
    excluded = {
        "EPS",
        "IAS",
        "IFRS",
        "PKR",
        "PLC",
        "SECP",
        "USD",
    }
    entities: list[str] = []
    for match in re.finditer(r"\b[A-Z][A-Z0-9&]{1,}(?:'[A-Z])?\b", text):
        entity = match.group(0).strip("'")
        if entity in excluded:
            continue
        if entity not in entities:
            entities.append(entity)
    return tuple(entities)


def _units_scale_text_from_rows(rows: tuple[tuple[str, ...], ...]) -> str | None:
    for row in rows[:12]:
        text = _row_text(row)
        normalized = text.lower()
        if _has_explicit_scale_marker(normalized) or "pkr" in normalized or "rs" in normalized:
            return text
    return None


def _units_scale_context_text(
    candidate_scale: str,
    candidate_unit: str,
    table_units_scale_text: str | None,
) -> str | None:
    values = [
        value
        for value in (table_units_scale_text, candidate_scale, candidate_unit)
        if value and value.lower() != "unknown"
    ]
    if not values:
        return None
    deduped: list[str] = []
    for value in values:
        if value not in deduped:
            deduped.append(value)
    return " | ".join(deduped)


def _merge_document_context(
    *,
    page_context: ExtractedTableDocumentContext,
    table_statement_title: str | None,
    table_notes_to_marker: bool,
    table_named_entities: tuple[str, ...],
    section_heading: str | None,
    units_scale_text: str | None,
) -> ExtractedTableDocumentContext:
    return ExtractedTableDocumentContext(
        statement_title=page_context.statement_title or table_statement_title,
        section_heading=section_heading,
        notes_to_marker=page_context.notes_to_marker or table_notes_to_marker,
        named_entities=_merge_named_entities(
            page_context.named_entities,
            table_named_entities,
        ),
        units_scale_text=units_scale_text,
        entity_context=page_context.entity_context,
    )


def _merge_named_entities(
    first: tuple[str, ...],
    second: tuple[str, ...],
) -> tuple[str, ...]:
    merged: list[str] = []
    for value in (*first, *second):
        if value not in merged:
            merged.append(value)
    return tuple(merged)


def _year_columns(row: tuple[str, ...]) -> dict[int, int]:
    years: dict[int, int] = {}
    for index, cell in enumerate(row):
        match = re.search(r"\b(19|20)\d{2}\b", cell)
        if match:
            years[index] = int(match.group(0))
    return years if len(years) >= 2 else {}


def _scale_from_row(
    row: tuple[str, ...],
    year_columns: dict[int, int],
) -> tuple[str, str] | tuple[None, None]:
    text = " ".join(cell for cell in row if cell).lower()
    if not text:
        return None, None
    if _label_percentage_not_scale(row, year_columns):
        return None, None
    if _looks_like_value_row(row, year_columns) and not _has_explicit_scale_marker(text):
        return None, None
    if "%" in text or "percent" in text:
        return "source_header:percentage", "%"
    if "pkr" in text or "rupee" in text or "rs" in text:
        if "million" in text:
            return "source_header:PKR millions", "PKR"
        if "'000" in text or "000" in text:
            return "source_header:PKR thousands", "PKR"
        return "source_header:PKR", "PKR"
    return None, None


def _scale_for_label(
    label: str,
    active_scale: str,
    active_unit: str,
) -> tuple[str, str]:
    normalized = label.lower()
    if ("earning" in normalized or "eps" in normalized) and "share" in normalized:
        return "source_header:full", "PKR_per_share"
    return active_scale, active_unit


def _has_explicit_scale_marker(text: str) -> bool:
    return any(
        marker in text
        for marker in (
            "million",
            "'000",
            " 000",
            "(000",
            "percent",
            "%",
        )
    )


def _looks_like_value_row(
    row: tuple[str, ...],
    year_columns: dict[int, int],
) -> bool:
    if year_columns:
        first_year_column = min(year_columns)
        leading_text = " ".join(cell for cell in row[:first_year_column] if cell).lower()
        if leading_text and _has_explicit_scale_marker(leading_text):
            return False
        observation_cells = [
            cell
            for index, cell in enumerate(row)
            if index not in year_columns and index >= first_year_column
        ]
    else:
        first_numeric = next(
            (index for index, cell in enumerate(row) if _is_numeric_value(cell)),
            None,
        )
        if first_numeric is None:
            return False
        leading_text = " ".join(cell for cell in row[:first_numeric] if cell).lower()
        if not leading_text:
            return False
        if _has_explicit_scale_marker(leading_text):
            return False
        observation_cells = list(row[first_numeric:])
    return any(_is_numeric_value(cell) for cell in observation_cells)


def _label_percentage_not_scale(
    row: tuple[str, ...],
    year_columns: dict[int, int],
) -> bool:
    if not year_columns:
        return False
    first_year_column = min(year_columns)
    leading_text = " ".join(cell for cell in row[:first_year_column] if cell).lower()
    value_text = " ".join(cell for cell in row[first_year_column:] if cell).lower()
    return "%" in leading_text and "%" not in value_text and any(
        _is_numeric_value(cell) for cell in row[first_year_column:]
    )


def _section_label_from_row(
    row: tuple[str, ...],
    year_columns: dict[int, int],
) -> str | None:
    if not year_columns:
        return None
    labels = [cell for index, cell in enumerate(row) if index not in year_columns and cell]
    label = " ".join(labels).strip(" ,")
    return label or None


def _section_is_percentage_analysis(section_label: str) -> bool:
    normalized = section_label.lower()
    compact = re.sub(r"\s+", "", normalized)
    return (
        "analysis" in normalized
        or "analysis" in compact
        or "%" in normalized
        or "year on year" in normalized
        or "yearonyear" in compact
    )


def _section_heading_from_row(
    row: tuple[str, ...],
    active_year_columns: dict[int, int],
) -> str | None:
    if not active_year_columns:
        return None
    first_year_column = min(active_year_columns)
    values = [
        row[column_index]
        for column_index in active_year_columns
        if column_index < len(row)
    ]
    if any(_is_numeric_value(value) for value in values):
        return None
    label = _label_from_row(row, first_year_column)
    if not label:
        return None
    if _has_explicit_scale_marker(label.lower()):
        return None
    return label


def _label_from_row(row: tuple[str, ...], first_year_column: int) -> str | None:
    label_cells = []
    for cell in row[:first_year_column]:
        if not cell:
            continue
        if _is_note_reference(cell):
            continue
        label_cells.append(cell)
    label = " ".join(label_cells)
    label = re.sub(r"\s+", " ", label).strip(" ,")
    return label or None


def _label_from_unlabeled_balance_sheet_subtotal(
    rows: tuple[tuple[str, ...], ...],
    row_index: int,
    active_year_columns: dict[int, int],
    active_section_label: str | None,
) -> str | None:
    if not active_year_columns:
        return None
    if not _is_current_liabilities_section(active_section_label):
        return None

    row = rows[row_index]
    first_year_column = min(active_year_columns)
    if _label_from_row(row, first_year_column):
        return None
    year_values = [
        row[column_index] if column_index < len(row) else ""
        for column_index in active_year_columns
    ]
    if not year_values or not all(_is_numeric_value(value) for value in year_values):
        return None
    if not _next_label_is_total_equity_and_liabilities(
        rows,
        row_index,
        active_year_columns,
    ):
        return None
    return "total_liabilities"


def _is_current_liabilities_section(section_label: str | None) -> bool:
    if not section_label:
        return False
    compact = _compact_alpha(section_label)
    if "liabilit" not in compact:
        return False
    if compact.startswith("noncurrent") or compact.startswith("oncurrent"):
        return False
    return compact.startswith("current") or compact.startswith("urrent")


def _next_label_is_total_equity_and_liabilities(
    rows: tuple[tuple[str, ...], ...],
    row_index: int,
    active_year_columns: dict[int, int],
) -> bool:
    first_year_column = min(active_year_columns)
    for next_row in rows[row_index + 1 : row_index + 4]:
        label = _label_from_row(next_row, first_year_column)
        if not label:
            if _has_numeric_year_values(next_row, active_year_columns):
                return False
            continue
        compact = _compact_alpha(label)
        return compact.startswith("totalequityandliabilities") or compact.startswith(
            "otalequityandliabilities"
        )
    return False


def _has_numeric_year_values(
    row: tuple[str, ...],
    active_year_columns: dict[int, int],
) -> bool:
    return any(
        column_index < len(row) and _is_numeric_value(row[column_index])
        for column_index in active_year_columns
    )


def _compact_alpha(value: str) -> str:
    return re.sub(r"[^a-z]+", "", value.lower())


def _is_note_reference(value: str) -> bool:
    normalized = value.replace(" ", "")
    if re.fullmatch(r"\d+(\.\d+)*\.?", normalized):
        return True
    if re.fullmatch(r"\d+(\.\d+)*(,\d+(\.\d+)*)*(?:&\d+(\.\d+)*)?", normalized):
        return True
    return False


def _is_numeric_value(value: str) -> bool:
    if not value:
        return False
    stripped = value.strip()
    if stripped in {"-", "- ", "–", "—"}:
        return False
    cleaned = stripped.replace(",", "").replace(" ", "")
    cleaned = cleaned.replace("(", "").replace(")", "").replace("%", "")
    cleaned = cleaned.replace("'", "")
    cleaned = cleaned.replace("–", "-").replace("—", "-")
    return bool(re.search(r"\d", cleaned)) and bool(re.fullmatch(r"-?\d+(?:\.\d+)?", cleaned))


__all__ = [
    "DEFAULT_BBOX_TABLES_DIR",
    "ExtractedTableDocumentContext",
    "ExtractedTableCell",
    "OCRV2RawTableIngestionResult",
    "OCRV2PageContextProvider",
    "OCRV2TableAdapter",
]
