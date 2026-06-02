"""Shared platform models used across financial intelligence engines."""

from .company_context import CompanyContext
from .financial_fact import FinancialFact
from .financial_year_consolidation import (
    ConsolidationCandidate,
    ConsolidationGroup,
    FinancialYearConsolidationResult,
)
from .historical_series_integrity import (
    CandidateSpreadEvidence,
    HistoricalSeriesIntegrityGateResult,
    HistoricalSeriesIntegrityIssue,
    HistoricalSeriesIntegrityResult,
    IntegrityEvidence,
    ScaleConsistencyResult,
    SeriesValueCandidateEvidence,
    YoYScaleEvidence,
)
from .metric_value import MetricValue
from .report import Report

__all__ = [
    "CandidateSpreadEvidence",
    "CompanyContext",
    "ConsolidationCandidate",
    "ConsolidationGroup",
    "FinancialFact",
    "FinancialYearConsolidationResult",
    "HistoricalSeriesIntegrityGateResult",
    "HistoricalSeriesIntegrityIssue",
    "HistoricalSeriesIntegrityResult",
    "IntegrityEvidence",
    "MetricValue",
    "Report",
    "ScaleConsistencyResult",
    "SeriesValueCandidateEvidence",
    "YoYScaleEvidence",
]
