"""Tests for the shared embedding metric normalizer."""

import logging
import sys
from pathlib import Path

import numpy as np
import pytest

BACKEND_DIR = Path(__file__).resolve().parents[3]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from shared.normalization.services.metric_normalizer import EmbeddingMetricNormalizer
from shared.normalization.services.similarity_search_service import SimilarityMatch


class FakeEmbeddingGenerator:
    def __init__(self, vectors: dict[str, list[float]] | None = None) -> None:
        self.vectors = vectors or {}
        self.calls: list[list[str]] = []

    def generate(self, texts: list[str]) -> np.ndarray:
        self.calls.append(list(texts))
        return np.array(
            [self.vectors.get(text, [0.0, 1.0]) for text in texts],
            dtype=float,
        )


class FixedSimilaritySearchService:
    def __init__(self, score: float, index: int = 0) -> None:
        self.score = score
        self.index = index

    def search_best(
        self,
        query_embedding: np.ndarray,
        candidate_embeddings: np.ndarray,
    ) -> SimilarityMatch:
        return SimilarityMatch(index=self.index, score=self.score)


def _registry() -> dict[str, dict[str, object]]:
    return {
        "revenue": {
            "display_name": "Revenue",
            "aliases": [
                "sales",
                "net sales",
                "turnover",
                "revenue from contracts with customers",
            ],
            "category": "income_statement",
        },
        "gross_profit": {
            "display_name": "Gross Profit",
            "aliases": ["gross income", "gross earnings"],
            "category": "income_statement",
        },
    }


def test_normalizer_uses_exact_match_without_embeddings(
    caplog: pytest.LogCaptureFixture,
) -> None:
    embedding_generator = FakeEmbeddingGenerator()
    normalizer = EmbeddingMetricNormalizer(
        canonical_metric_registry=_registry(),
        embedding_generator=embedding_generator,
    )

    with caplog.at_level(logging.DEBUG):
        result = normalizer.normalize_metric("Revenue")

    assert result.model_dump() == {
        "original_metric": "Revenue",
        "normalized_metric": "revenue",
        "confidence": 1.0,
        "requires_review": False,
    }
    assert "Metric Found Via Exact Match" in caplog.text
    assert embedding_generator.calls == []


def test_normalizer_uses_alias_match() -> None:
    normalizer = EmbeddingMetricNormalizer(
        canonical_metric_registry=_registry(),
        embedding_generator=FakeEmbeddingGenerator(),
    )

    result = normalizer.normalize_metric("Net Sales")

    assert result.normalized_metric == "revenue"
    assert result.confidence == 0.96
    assert result.requires_review is False


def test_normalizer_uses_embedding_similarity_for_unknown_metric() -> None:
    vectors = {
        "revenue": [0.0, 1.0],
        "Revenue": [0.0, 1.0],
        "sales": [0.0, 1.0],
        "net sales": [0.0, 1.0],
        "turnover": [0.0, 1.0],
        "revenue from contracts with customers": [0.0, 1.0],
        "gross_profit": [1.0, 0.0],
        "Gross Profit": [1.0, 0.0],
        "gross income": [1.0, 0.0],
        "gross earnings": [1.0, 0.0],
        "Gross margin": [1.0, 0.0],
    }
    normalizer = EmbeddingMetricNormalizer(
        canonical_metric_registry=_registry(),
        embedding_generator=FakeEmbeddingGenerator(vectors=vectors),
    )

    result = normalizer.normalize_metric("Gross margin")

    assert result.normalized_metric == "gross_profit"
    assert result.confidence == 1.0
    assert result.requires_review is False


def test_medium_confidence_embedding_match_normalizes_with_debug_log(
    caplog: pytest.LogCaptureFixture,
) -> None:
    normalizer = EmbeddingMetricNormalizer(
        canonical_metric_registry=_registry(),
        embedding_generator=FakeEmbeddingGenerator(),
        similarity_search_service=FixedSimilaritySearchService(score=0.85),
    )

    with caplog.at_level(logging.DEBUG):
        result = normalizer.normalize_metric("Top line")

    assert result.normalized_metric == "revenue"
    assert result.confidence == 0.85
    assert result.requires_review is False
    assert "Metric Found Via Embedding Search" in caplog.text


def test_low_confidence_embedding_match_requires_review(
    caplog: pytest.LogCaptureFixture,
) -> None:
    normalizer = EmbeddingMetricNormalizer(
        canonical_metric_registry=_registry(),
        embedding_generator=FakeEmbeddingGenerator(),
        similarity_search_service=FixedSimilaritySearchService(score=0.79),
    )

    with caplog.at_level(logging.WARNING):
        result = normalizer.normalize_metric("Unclear OCR Label")

    assert result.normalized_metric is None
    assert result.confidence == 0.79
    assert result.requires_review is True
    assert "Metric Requires Review" in caplog.text


def test_candidate_embeddings_are_cached() -> None:
    embedding_generator = FakeEmbeddingGenerator()
    normalizer = EmbeddingMetricNormalizer(
        canonical_metric_registry=_registry(),
        embedding_generator=embedding_generator,
        similarity_search_service=FixedSimilaritySearchService(score=0.85),
    )

    normalizer.normalize_metric("Top line")
    normalizer.normalize_metric("Total turnover equivalent")

    assert len(embedding_generator.calls) == 3
    assert len(embedding_generator.calls[0]) > 1
    assert embedding_generator.calls[1] == ["Top line"]
    assert embedding_generator.calls[2] == ["Total turnover equivalent"]


def test_normalizer_rejects_empty_metric_names() -> None:
    normalizer = EmbeddingMetricNormalizer(
        canonical_metric_registry=_registry(),
        embedding_generator=FakeEmbeddingGenerator(),
    )

    with pytest.raises(ValueError, match="non-empty"):
        normalizer.normalize_metric(" ")


@pytest.mark.parametrize(
    ("label", "expected_metric"),
    [
        ("(Other Income)/Charges", "other_income"),
        ("Administrative Cost", "administrative_expenses"),
        ("Noncurrent Assets", "non_current_assets"),
        ("Noncurrent Liabilities", "non_current_liabilities"),
        ("Operating Cycle days", "operating_cycle"),
        ("Share Capital & Reserves", "share_capital_and_reserves"),
        ("Total Equity & Liabilities", "total_equity_and_liabilities"),
        (
            "Investment Valuation Ratios - Market Value Per Share as on 30th June rupees",
            "market_value_per_share",
        ),
        ("Total Net Sales", "revenue"),
        ("Reported Net Sales", "revenue"),
        ("Net Sales Amount", "revenue"),
        (
            "Employee Productivity Ratios - Revenue per Employee rupees in MN",
            "revenue_per_employee",
        ),
        ("Non-Financial Ratios - % of Plant Availability", "plant_availability"),
        ("Particulars - Managerial remuneration", "managerial_remuneration"),
    ],
)
def test_default_registry_normalizes_lucky_cement_labels(
    label: str,
    expected_metric: str,
) -> None:
    embedding_generator = FakeEmbeddingGenerator()
    normalizer = EmbeddingMetricNormalizer(embedding_generator=embedding_generator)

    result = normalizer.normalize_metric(label)

    assert result.normalized_metric == expected_metric
    assert result.requires_review is False
    assert embedding_generator.calls == []


@pytest.mark.parametrize(
    ("label", "expected_metric"),
    [
        ("Operating Profi", "operating_profit"),
        ("Earnings Per S", "earnings_per_share"),
        ("GP as % of Net", "gross_margin"),
        ("NP (Attributabl", "net_income"),
        (
            "Current assets excluding cash and cash equivalents",
            "current_assets_excluding_cash_and_cash_equivalents",
        ),
        (
            "Investment Valuation Ratios - i) Without surplus on Revaluation of property rupees",
            "break_up_value_per_share_without_surplus",
        ),
        (
            "Investment Valuation Ratios - ii) With Surplus on Revaluation of PPE including all rupees",
            "break_up_value_per_share_with_surplus",
        ),
        (
            "Investment Valuation Ratios - iii) Including investment in related party at fair rupees",
            "break_up_value_per_share_with_related_party_fair_value",
        ),
        (
            "REMUNERATION OF CHIEF EX ECU - Managerial remuneration",
            "chief_executive_remuneration",
        ),
        (
            "Aggre gate amo unts char g - Managerial remuneration",
            "managerial_remuneration",
        ),
        ("Other b enefits - Number of persons", "employee_count"),
        ("Fair value of plan assets", "fair_value_of_plan_assets"),
        (
            "Historical in formation – funded plans - Net liability / (asset)",
            "defined_benefit_net_liability_asset",
        ),
        ("Pension Grat uity - Government bonds", "defined_benefit_government_bonds"),
        ("Pension Grat uity - Cash and term deposits", "defined_benefit_cash_term_deposits"),
        ("The Group’s share of net assets (50%)", "share_of_net_assets"),
        ("The Group’s share of net profit (50%)", "share_of_net_profit"),
        ("Net loss (100%)", "share_of_net_loss"),
    ],
)
def test_default_registry_normalizes_lucky_final_coverage_labels(
    label: str,
    expected_metric: str,
) -> None:
    embedding_generator = FakeEmbeddingGenerator()
    normalizer = EmbeddingMetricNormalizer(embedding_generator=embedding_generator)

    result = normalizer.normalize_metric(label)

    assert result.normalized_metric == expected_metric
    assert result.requires_review is False
    assert embedding_generator.calls == []


@pytest.mark.parametrize(
    ("label", "expected_metric"),
    [
        ("Cash and cash equivale nts", "cash_and_cash_equivalents"),
        ("Cash and cash eq uivalents", "cash_and_cash_equivalents"),
        ("ash and cash e quivalents at the b eginning of the year", "cash_at_beginning_of_period"),
        ("cash and cash equivalent at the beginning of the", "cash_at_beginning_of_period"),
        ("ash and cash e quivalents at the e nd of the year", "cash_at_end_of_period"),
        ("cash and cash equivalent at the end of the", "cash_at_end_of_period"),
        ("ash genera ted f rom operations", "cash_generated_from_operations"),
        ("et cash gen erat ed from operating activities", "operating_cash_flow"),
        ("OTAL ASSETS", "total_assets"),
        ("OTAL EQUITY AND LIABILITIES", "total_equity_and_liabilities"),
        ("Operating exp ense s", "operating_expenses"),
        ("Amortisation", "amortization_expense"),
        ("Current assets exc luding cash and cash equivalents", "current_assets_excluding_cash_and_cash_equivalents"),
        ("Current service cost", "defined_benefit_current_service_cost"),
        ("Authorised capital - Ordinary shares of P KR 2/\u2013 each", "ordinary_shares"),
        ("Note 2025 2024 - Net profit (100%", "share_of_net_profit"),
        ("Accretion of intere st o n lease liabilities", "finance_cost"),
        ("Advances fro m cust omers / cont ract liabilities", "contract_liabilities"),
        ("Transfer from capital work i n pr ogress", "transfer_from_capital_work_in_progress"),
    ],
)
def test_default_registry_normalizes_dirty_ocr_aliases(
    label: str,
    expected_metric: str,
) -> None:
    embedding_generator = FakeEmbeddingGenerator()
    normalizer = EmbeddingMetricNormalizer(embedding_generator=embedding_generator)

    result = normalizer.normalize_metric(label)

    assert result.normalized_metric == expected_metric
    assert result.requires_review is False
    assert embedding_generator.calls == []


@pytest.mark.parametrize(
    ("label", "expected_metric"),
    [
        ("Salaries and amenities", "staff_cost"),
        ("Cash and bank balance", "cash_and_bank_balances"),
        ("Trade and other payables", "creditors_accrued_other_liabilities"),
        ("Loans to employees", "loans_to_employees"),
        ("Long term investments", "long_term_investments"),
        ("Distribution Cost", "distribution_expenses"),
        ("Operating Profit", "operating_profit"),
    ],
)
def test_default_registry_normalizes_millat_labels(
    label: str,
    expected_metric: str,
) -> None:
    embedding_generator = FakeEmbeddingGenerator()
    normalizer = EmbeddingMetricNormalizer(embedding_generator=embedding_generator)

    result = normalizer.normalize_metric(label)

    assert result.normalized_metric == expected_metric
    assert result.requires_review is False
    assert embedding_generator.calls == []
