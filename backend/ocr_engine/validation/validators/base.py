"""Shared parsing and rule helpers for financial validation validators."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections import Counter
from dataclasses import dataclass
import logging
import re
from typing import Iterable, Mapping, Sequence

import pandas as pd

from ocr_engine.models.financial_table_classification import (
    FinancialTableClassificationResult,
)
from ocr_engine.models.table_extraction import ExtractedTable, TableExtractionResult
from ocr_engine.models.validation_result import ValidationIssue

logger = logging.getLogger(__name__)

BALANCE_SHEET_TABLE_TYPES = (
    "balance_sheet",
    "statement_of_financial_position",
    "financial_position",
)
INCOME_STATEMENT_TABLE_TYPES = (
    "income_statement",
    "profit_and_loss",
    "statement_of_profit_or_loss",
    "statement_of_comprehensive_income",
)
CASH_FLOW_TABLE_TYPES = (
    "cash_flow",
    "cash_flow_statement",
    "statement_of_cash_flows",
)
EQUITY_TABLE_TYPES = (
    "statement_of_changes_in_equity",
    "equity",
    "retained_earnings",
)
PPE_TABLE_TYPES = (
    "property_plant_equipment_note",
    "ppe_note",
    "fixed_assets_note",
    "property_plant_and_equipment",
)
DEBT_TABLE_TYPES = (
    "debt_schedule",
    "borrowings_note",
    "loan_note",
    "financing_note",
)

METRIC_ALIASES: Mapping[str, tuple[str, ...]] = {
    "total_assets": (
        "total assets",
        "assets",
        "total asset",
    ),
    "current_assets": (
        "current assets",
        "total current assets",
        "current asset",
    ),
    "non_current_assets": (
        "non current assets",
        "non-current assets",
        "total non current assets",
        "total non-current assets",
    ),
    "cash": (
        "cash and bank balances",
        "cash and cash equivalents",
        "cash in hand and at banks",
        "cash and balances with banks",
        "cash and bank",
        "cash",
        "bank balances",
    ),
    "inventory": (
        "stock in trade",
        "stores spares and loose tools",
        "stores and spares",
        "inventories",
        "inventory",
        "stock",
    ),
    "trade_receivables": (
        "trade debts",
        "trade receivables",
        "trade and other receivables",
        "accounts receivable",
        "receivables",
    ),
    "other_current_assets": (
        "other current assets",
        "advances deposits prepayments and other receivables",
        "loans advances deposits prepayments and other receivables",
        "short term prepayments",
        "other receivables",
    ),
    "total_liabilities": (
        "total liabilities",
        "liabilities",
        "total liability",
    ),
    "current_liabilities": (
        "current liabilities",
        "total current liabilities",
        "current liability",
    ),
    "non_current_liabilities": (
        "non current liabilities",
        "non-current liabilities",
        "total non current liabilities",
        "total non-current liabilities",
    ),
    "trade_payables": (
        "trade and other payables",
        "trade payables",
        "creditors accrued and other liabilities",
        "creditors accrued expenses and other liabilities",
        "accounts payable",
        "payables",
    ),
    "short_term_borrowings": (
        "short term borrowings",
        "short-term borrowings",
        "short term finances",
        "running finance",
        "short term loans",
    ),
    "current_portion_of_debt": (
        "current portion of long term debt",
        "current portion of long-term financing",
        "current maturity of long term financing",
        "current portion of debt",
        "current maturity of debt",
    ),
    "other_current_liabilities": (
        "other current liabilities",
        "accrued liabilities",
        "accrued expenses",
        "unclaimed dividend",
    ),
    "total_equity": (
        "total equity",
        "shareholders equity",
        "shareholders' equity",
        "equity attributable to owners",
        "equity",
    ),
    "share_capital": (
        "share capital",
        "issued subscribed and paid up capital",
        "issued subscribed and paid-up capital",
        "paid up capital",
        "ordinary share capital",
    ),
    "reserves": (
        "capital reserves",
        "revenue reserves",
        "revaluation surplus",
        "surplus on revaluation of fixed assets",
        "reserves",
    ),
    "retained_earnings": (
        "retained earnings",
        "unappropriated profit",
        "accumulated profit",
        "accumulated losses",
    ),
    "revenue": (
        "revenue from contracts with customers",
        "sales revenue",
        "net sales",
        "turnover",
        "revenue",
        "sales",
    ),
    "cost_of_sales": (
        "cost of sales",
        "cost of goods sold",
        "cost of revenue",
        "cost of services",
        "cost of products sold",
    ),
    "gross_profit": (
        "gross profit",
        "gross income",
        "gross margin amount",
    ),
    "operating_expenses": (
        "operating expenses",
        "selling distribution and administrative expenses",
        "distribution and administrative expenses",
        "selling and distribution expenses",
        "administrative expenses",
        "distribution costs",
    ),
    "operating_profit": (
        "operating profit",
        "profit from operations",
        "profit before other income and finance cost",
        "operating income",
    ),
    "other_income": (
        "other income",
        "other operating income",
        "other gains",
        "other income net",
    ),
    "ebit": (
        "earnings before interest and tax",
        "earnings before interest and taxes",
        "profit before finance cost and taxation",
        "profit before finance cost and tax",
        "ebit",
    ),
    "finance_cost": (
        "finance cost",
        "finance costs",
        "financial charges",
        "mark up expense",
        "markup expense",
        "interest expense",
    ),
    "profit_before_tax": (
        "profit before taxation",
        "profit before tax",
        "profit before income tax",
        "pbt",
    ),
    "tax_expense": (
        "taxation",
        "tax expense",
        "income tax expense",
        "provision for taxation",
        "tax",
    ),
    "profit_after_tax": (
        "profit after taxation",
        "profit after tax",
        "profit for the year",
        "profit for the period",
        "net profit after tax",
        "net income",
        "pat",
    ),
    "operating_cash_flow": (
        "net cash generated from operating activities",
        "net cash from operating activities",
        "cash generated from operations",
        "cash flows from operating activities",
        "operating cash flow",
    ),
    "investing_cash_flow": (
        "net cash used in investing activities",
        "net cash from investing activities",
        "cash flows from investing activities",
        "investing cash flow",
    ),
    "financing_cash_flow": (
        "net cash used in financing activities",
        "net cash from financing activities",
        "cash flows from financing activities",
        "financing cash flow",
    ),
    "net_change_in_cash": (
        "net increase in cash and cash equivalents",
        "net decrease in cash and cash equivalents",
        "net change in cash and cash equivalents",
        "increase decrease in cash and cash equivalents",
        "net change in cash",
    ),
    "opening_cash": (
        "cash and cash equivalents at beginning of year",
        "cash and cash equivalents at beginning of the year",
        "cash and cash equivalents at start of year",
        "cash at beginning of year",
        "opening cash",
    ),
    "closing_cash": (
        "cash and cash equivalents at end of year",
        "cash and cash equivalents at end of the year",
        "cash and cash equivalents at close of year",
        "cash at end of year",
        "closing cash",
    ),
    "beginning_retained_earnings": (
        "retained earnings at beginning of year",
        "unappropriated profit at beginning of year",
        "opening retained earnings",
        "opening unappropriated profit",
    ),
    "ending_retained_earnings": (
        "retained earnings at end of year",
        "unappropriated profit at end of year",
        "closing retained earnings",
        "closing unappropriated profit",
    ),
    "dividends": (
        "dividend paid",
        "dividends paid",
        "final dividend",
        "cash dividend",
        "dividend",
    ),
    "beginning_ppe": (
        "property plant and equipment at beginning of year",
        "opening property plant and equipment",
        "opening written down value",
        "opening carrying amount",
        "beginning ppe",
    ),
    "ending_ppe": (
        "property plant and equipment at end of year",
        "closing property plant and equipment",
        "closing written down value",
        "closing carrying amount",
        "ending ppe",
    ),
    "capex": (
        "capital expenditure",
        "additions to property plant and equipment",
        "additions during the year",
        "additions",
        "capex",
    ),
    "depreciation": (
        "depreciation charge for the year",
        "depreciation for the year",
        "depreciation charge",
        "depreciation",
    ),
    "beginning_debt": (
        "debt at beginning of year",
        "opening borrowings",
        "opening debt",
        "beginning debt",
    ),
    "ending_debt": (
        "debt at end of year",
        "closing borrowings",
        "closing debt",
        "ending debt",
        "total debt",
    ),
    "new_borrowings": (
        "new borrowings",
        "loans obtained",
        "proceeds from borrowings",
        "proceeds from long term financing",
        "drawdowns",
    ),
    "repayments": (
        "repayment of borrowings",
        "repayment of long term financing",
        "loan repayments",
        "repayments",
    ),
    "eps": (
        "earnings per share basic",
        "basic earnings per share",
        "earnings per share",
        "eps",
    ),
    "weighted_average_shares": (
        "weighted average number of ordinary shares",
        "weighted average shares",
        "weighted average number of shares",
        "average shares",
    ),
    "roe": (
        "return on equity",
        "roe",
    ),
    "average_equity": (
        "average shareholders equity",
        "average shareholders' equity",
        "average equity",
    ),
    "current_ratio": (
        "current ratio",
        "liquidity ratio",
    ),
}


@dataclass(frozen=True)
class MetricObservation:
    """A normalized metric value parsed from one extracted table row."""

    metric_name: str
    label: str
    value: float
    values: tuple[float, ...]
    page_number: int
    table_type: str
    table_index: int
    row_index: int

    @property
    def source_id(self) -> str:
        """Return a stable source identifier for logging and debugging."""

        return f"p{self.page_number}:t{self.table_index}:r{self.row_index}"


@dataclass(frozen=True)
class MetricRef:
    """Reference to a metric, optionally constrained to table type aliases."""

    name: str
    table_types: tuple[str, ...] | None = None


@dataclass(frozen=True)
class ValidationContext:
    """Parsed financial data and source tables used by validation rules."""

    classification_result: FinancialTableClassificationResult
    table_extraction_result: TableExtractionResult
    observations: tuple[MetricObservation, ...]
    table_dataframes: Mapping[tuple[int, int], pd.DataFrame]
    labels_by_table: Mapping[tuple[int, int], tuple[str, ...]]
    year_sequences_by_table: Mapping[tuple[int, int], tuple[tuple[int, ...], ...]]
    tables_by_key: Mapping[tuple[int, int], ExtractedTable]

    def observations_for(
        self,
        metric_name: str,
        table_types: Sequence[str] | None = None,
    ) -> tuple[MetricObservation, ...]:
        """Return observations matching a canonical metric and table type group."""

        matches = [
            observation
            for observation in self.observations
            if observation.metric_name == metric_name
        ]
        if table_types is not None:
            matches = [
                observation
                for observation in matches
                if table_type_matches(observation.table_type, table_types)
            ]

        return tuple(matches)

    def value_for(
        self,
        metric_name: str,
        table_types: Sequence[str] | None = None,
    ) -> float | None:
        """Return the first current-period value for a canonical metric."""

        observations = self.observations_for(metric_name, table_types)
        if not observations:
            return None
        return observations[0].value

    def has_metric(
        self,
        metric_names: Iterable[str],
        table_types: Sequence[str] | None = None,
    ) -> bool:
        """Return whether any canonical metric is present in the context."""

        return any(self.value_for(metric_name, table_types) is not None for metric_name in metric_names)

    def labels_for(
        self,
        table_types: Sequence[str] | None = None,
    ) -> tuple[str, ...]:
        """Return normalized labels filtered by table type group."""

        labels: list[str] = []
        for key, table_labels in self.labels_by_table.items():
            table = self.tables_by_key[key]
            if table_types is None or table_type_matches(table.table_type, table_types):
                labels.extend(table_labels)
        return tuple(labels)


class RuleValidator(ABC):
    """Base contract for financial validation rule groups."""

    @abstractmethod
    def validate(self, context: ValidationContext) -> list[ValidationIssue]:
        """Return all issues found by this rule group."""


def build_validation_context(
    classification_result: FinancialTableClassificationResult,
    table_extraction_result: TableExtractionResult,
) -> ValidationContext:
    """Parse extracted table rows into canonical metric observations."""

    observations: list[MetricObservation] = []
    table_dataframes: dict[tuple[int, int], pd.DataFrame] = {}
    labels_by_table: dict[tuple[int, int], tuple[str, ...]] = {}
    year_sequences_by_table: dict[tuple[int, int], tuple[tuple[int, ...], ...]] = {}
    tables_by_key: dict[tuple[int, int], ExtractedTable] = {}

    for table in table_extraction_result.tables:
        key = (table.page_number, table.table_index)
        table_dataframes[key] = pd.DataFrame(table.rows)
        tables_by_key[key] = table

        labels: list[str] = []
        year_sequences: list[tuple[int, ...]] = []

        for row_index, row in enumerate(table.rows):
            year_sequence = extract_year_sequence(row)
            if len(year_sequence) >= 2:
                year_sequences.append(tuple(year_sequence))

            label_index, label = extract_label(row)
            if label is None:
                continue

            normalized_label = normalize_text(label)
            labels.append(normalized_label)
            metric_name = canonical_metric_name(label)
            if metric_name is None:
                continue

            values = extract_numeric_values(row, label_index)
            if not values:
                continue

            observations.append(
                MetricObservation(
                    metric_name=metric_name,
                    label=label,
                    value=values[0],
                    values=tuple(values),
                    page_number=table.page_number,
                    table_type=table.table_type,
                    table_index=table.table_index,
                    row_index=row_index,
                )
            )

        labels_by_table[key] = tuple(labels)
        year_sequences_by_table[key] = tuple(year_sequences)

    logger.debug(
        "Parsed validation context",
        extra={
            "tables": len(table_extraction_result.tables),
            "observations": len(observations),
        },
    )

    return ValidationContext(
        classification_result=classification_result,
        table_extraction_result=table_extraction_result,
        observations=tuple(observations),
        table_dataframes=table_dataframes,
        labels_by_table=labels_by_table,
        year_sequences_by_table=year_sequences_by_table,
        tables_by_key=tables_by_key,
    )


def validate_arithmetic_rule(
    context: ValidationContext,
    rule_name: str,
    actual_ref: MetricRef,
    terms: Sequence[tuple[MetricRef, float]],
    severity: str,
    message: str,
) -> ValidationIssue | None:
    """Validate an arithmetic formula such as A = B + C - D."""

    actual = metric_value(context, actual_ref)
    term_values: list[float] = []

    for metric_ref, multiplier in terms:
        value = metric_value(context, metric_ref)
        if value is None:
            return None
        term_values.append(value * multiplier)

    if actual is None:
        return None

    expected = sum(term_values)
    if amounts_match(expected, actual):
        return None

    return make_issue(
        rule_name=rule_name,
        expected=round_number(expected),
        actual=round_number(actual),
        severity=severity,
        message=message,
    )


def validate_ratio_rule(
    context: ValidationContext,
    rule_name: str,
    actual_ref: MetricRef,
    numerator_ref: MetricRef,
    denominator_ref: MetricRef,
    severity: str,
    message: str,
) -> ValidationIssue | None:
    """Validate a ratio formula such as EPS = profit / shares."""

    actual = metric_value(context, actual_ref)
    numerator = metric_value(context, numerator_ref)
    denominator = metric_value(context, denominator_ref)

    if actual is None or numerator is None or denominator is None:
        return None

    if denominator == 0:
        return make_issue(
            rule_name=rule_name,
            expected="non-zero denominator",
            actual=0.0,
            severity=severity,
            message=f"{message} Denominator cannot be zero.",
        )

    expected = numerator / denominator
    comparable_actual = actual

    if not amounts_match(expected, comparable_actual, absolute_tolerance=0.0001):
        if abs(expected) <= 1 and abs(actual) > 1:
            comparable_actual = actual / 100

    if amounts_match(expected, comparable_actual, absolute_tolerance=0.0001):
        return None

    return make_issue(
        rule_name=rule_name,
        expected=round_number(expected),
        actual=round_number(actual),
        severity=severity,
        message=message,
    )


def metric_value(context: ValidationContext, metric_ref: MetricRef) -> float | None:
    """Resolve a metric reference to its first current-period value."""

    return context.value_for(metric_ref.name, metric_ref.table_types)


def make_issue(
    rule_name: str,
    expected: float | str | None,
    actual: float | str | None,
    severity: str,
    message: str,
) -> ValidationIssue:
    """Create a validation issue with normalized severity."""

    return ValidationIssue(
        rule_name=rule_name,
        expected=expected,
        actual=actual,
        severity=severity.lower(),
        message=message,
    )


def duplicate_labels(labels: Sequence[str]) -> tuple[str, ...]:
    """Return duplicate normalized labels from one source table."""

    counts = Counter(label for label in labels if label)
    return tuple(sorted(label for label, count in counts.items() if count > 1))


def labels_contain_any(labels: Iterable[str], keywords: Sequence[str]) -> bool:
    """Return whether any label contains one of the supplied phrases."""

    normalized_keywords = tuple(normalize_text(keyword) for keyword in keywords)
    return any(
        any(keyword in label for keyword in normalized_keywords)
        for label in labels
    )


def amounts_match(
    expected: float,
    actual: float,
    absolute_tolerance: float = 1.0,
    relative_tolerance: float = 0.01,
) -> bool:
    """Compare numeric values using absolute and percentage tolerance."""

    tolerance = max(absolute_tolerance, abs(expected) * relative_tolerance)
    return abs(expected - actual) <= tolerance


def round_number(value: float) -> float:
    """Round numbers for stable validation issue output."""

    return round(float(value), 4)


def table_type_matches(table_type: str, candidates: Sequence[str]) -> bool:
    """Return whether a table type matches any candidate table type alias."""

    table_type_key = normalize_identifier(table_type)
    for candidate in candidates:
        candidate_key = normalize_identifier(candidate)
        if (
            table_type_key == candidate_key
            or candidate_key in table_type_key
            or table_type_key in candidate_key
        ):
            return True
    return False


def canonical_metric_name(label: str) -> str | None:
    """Map a raw row label to a canonical metric name."""

    normalized_label = normalize_text(label)
    for metric_name, normalized_alias in _alias_lookup():
        if alias_matches_label(normalized_label, normalized_alias):
            return metric_name
    return None


def alias_matches_label(normalized_label: str, normalized_alias: str) -> bool:
    """Return whether a normalized alias matches a normalized OCR row label."""

    if not normalized_label or not normalized_alias:
        return False
    if normalized_label == normalized_alias:
        return True

    alias_tokens = normalized_alias.split()
    if len(alias_tokens) == 1:
        return False

    padded_label = f" {normalized_label} "
    padded_alias = f" {normalized_alias} "
    return padded_alias in padded_label


def _alias_lookup() -> tuple[tuple[str, str], ...]:
    """Return aliases ordered longest first to avoid premature broad matches."""

    lookup: list[tuple[str, str]] = []
    for metric_name, aliases in METRIC_ALIASES.items():
        for alias in aliases:
            lookup.append((metric_name, normalize_text(alias)))

    lookup.sort(key=lambda item: len(item[1]), reverse=True)
    return tuple(lookup)


def extract_label(row: Sequence[str]) -> tuple[int, str | None]:
    """Return the first text-like cell from an extracted row."""

    for index, cell in enumerate(row):
        text = str(cell).strip()
        if not text:
            continue
        if re.search(r"[A-Za-z]", text):
            return index, text
    return -1, None


def extract_numeric_values(row: Sequence[str], label_index: int) -> tuple[float, ...]:
    """Extract numeric values from a row while preserving left-to-right order."""

    values: list[float] = []
    for index, cell in enumerate(row):
        text = str(cell).strip()
        if index == label_index and not re.search(r"\d", text):
            continue

        value = parse_number(text)
        if value is not None and not is_year_cell(text):
            values.append(value)

    return tuple(values)


def extract_year_sequence(row: Sequence[str]) -> tuple[int, ...]:
    """Extract year-like values from one table row."""

    years: list[int] = []
    for cell in row:
        for match in re.finditer(r"\b(?:19|20)\d{2}\b", str(cell)):
            years.append(int(match.group(0)))
    return tuple(years)


def years_are_descending(years: Sequence[int]) -> bool:
    """Return whether a year sequence is strictly descending."""

    if len(years) < 2:
        return True
    return all(left > right for left, right in zip(years, years[1:]))


def parse_number(value: object) -> float | None:
    """Parse OCR text into a float using financial statement conventions."""

    if value is None:
        return None

    text = str(value).strip()
    if not text:
        return None

    normalized = normalize_text(text)
    if normalized in {"", "-", "na", "n a", "nil", "none"}:
        return None

    negative = "(" in text and ")" in text
    percent = "%" in text
    cleaned = (
        text.replace(",", "")
        .replace("\u2212", "-")
        .replace("(", "")
        .replace(")", "")
    )
    cleaned = re.sub(
        r"(?i)\b(rs|pkr|usd|eur|gbp|rupees|rupee|million|mn|billion|bn)\b\.?",
        " ",
        cleaned,
    )

    match = re.search(r"[-+]?\d+(?:\.\d+)?", cleaned)
    if match is None:
        return None

    number = float(match.group(0))
    if negative:
        number = -abs(number)
    if percent:
        number = number / 100
    return number


def is_year_cell(value: str) -> bool:
    """Return whether a cell contains only a standalone reporting year."""

    cleaned = value.strip().replace(",", "")
    return re.fullmatch(r"(?:19|20)\d{2}", cleaned) is not None


def normalize_identifier(value: str) -> str:
    """Normalize a table type or identifier to snake-case-like text."""

    return normalize_text(value).replace(" ", "_")


def normalize_text(value: str) -> str:
    """Normalize OCR text for alias and label matching."""

    normalized = value.lower().replace("&", " and ")
    normalized = re.sub(r"[^a-z0-9]+", " ", normalized)
    normalized = re.sub(r"\s+", " ", normalized)
    return normalized.strip()
