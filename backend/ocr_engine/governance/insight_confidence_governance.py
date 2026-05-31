"""Confidence governance for LLM-generated business insights."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
import json
from pathlib import Path
import re
from typing import Any

from ocr_engine.constants.insights_constants import (
    GENERIC_INSIGHT_FILTER_PATTERNS,
    INSIGHT_CONFIDENCE_REJECT_THRESHOLD,
    INSIGHT_CONFIDENCE_REVIEW_THRESHOLD,
    QUANTITATIVE_EVIDENCE_TERMS,
)

INSIGHT_ROUTE_EXPORT = "export"
INSIGHT_ROUTE_REVIEW = "review"
INSIGHT_ROUTE_REJECT = "reject"


@dataclass(frozen=True)
class InsightGovernanceDecision:
    """Routing decision for one generated insight."""

    insight: Any
    route: str
    reason: str
    has_quantitative_evidence: bool
    matched_generic_patterns: tuple[str, ...] = ()


@dataclass(frozen=True)
class InsightGovernanceResult:
    """Grouped insight routing results for workbook and diagnostics."""

    decisions: list[InsightGovernanceDecision] = field(default_factory=list)

    @property
    def exported_insights(self) -> list[Any]:
        """Insights eligible for the main Insights workbook sheet."""

        return [
            decision.insight
            for decision in self.decisions
            if decision.route == INSIGHT_ROUTE_EXPORT
        ]

    @property
    def review_insights(self) -> list[Any]:
        """Insights requiring analyst review before main-sheet export."""

        return [
            decision.insight
            for decision in self.decisions
            if decision.route == INSIGHT_ROUTE_REVIEW
        ]

    @property
    def rejected_insights(self) -> list[Any]:
        """Insights removed from workbook output by confidence governance."""

        return [
            decision.insight
            for decision in self.decisions
            if decision.route == INSIGHT_ROUTE_REJECT
        ]

    @property
    def rejected_low_confidence_count(self) -> int:
        """Number of insights rejected by confidence or generic filtering."""

        return len(self.rejected_insights)

    @property
    def review_bucket_count(self) -> int:
        """Number of insights routed to the review workbook sheet."""

        return len(self.review_insights)

    @property
    def exported_high_confidence_count(self) -> int:
        """Number of insights routed to the main Insights workbook sheet."""

        return len(self.exported_insights)

    @property
    def generic_filtered_count(self) -> int:
        """Number of rejected insights matching generic boilerplate patterns."""

        return sum(
            1
            for decision in self.decisions
            if decision.route == INSIGHT_ROUTE_REJECT
            and decision.matched_generic_patterns
        )

    @property
    def confidence_distribution(self) -> dict[str, int]:
        """Return stable confidence bucket counts for all governed insights."""

        counter: Counter[str] = Counter(
            _confidence_bucket(decision.insight.confidence)
            for decision in self.decisions
        )
        return {
            "0.0": counter.get("0.0", 0),
            "0.1-0.5": counter.get("0.1-0.5", 0),
            "0.5-0.7": counter.get("0.5-0.7", 0),
            "0.7-0.9": counter.get("0.7-0.9", 0),
            "0.9+": counter.get("0.9+", 0),
        }

    def to_audit_payload(self) -> dict[str, object]:
        """Return a JSON-serializable governance audit payload."""

        return {
            "total_insights": len(self.decisions),
            "insights_rejected_by_confidence": [
                _decision_payload(decision)
                for decision in self.decisions
                if decision.route == INSIGHT_ROUTE_REJECT
                and decision.reason == "confidence_below_reject_threshold"
            ],
            "insights_moved_to_review": [
                _decision_payload(decision)
                for decision in self.decisions
                if decision.route == INSIGHT_ROUTE_REVIEW
            ],
            "insights_filtered_as_generic": [
                _decision_payload(decision)
                for decision in self.decisions
                if decision.route == INSIGHT_ROUTE_REJECT
                and decision.matched_generic_patterns
            ],
            "final_exported_insight_count": self.exported_high_confidence_count,
            "review_bucket_count": self.review_bucket_count,
            "rejected_low_confidence_count": self.rejected_low_confidence_count,
            "generic_filtered_count": self.generic_filtered_count,
            "confidence_distribution": self.confidence_distribution,
            "thresholds": {
                "reject_threshold": INSIGHT_CONFIDENCE_REJECT_THRESHOLD,
                "review_threshold": INSIGHT_CONFIDENCE_REVIEW_THRESHOLD,
            },
        }


class InsightConfidenceGovernance:
    """Route LLM-generated insights by confidence and information quality."""

    def __init__(
        self,
        *,
        reject_threshold: float = INSIGHT_CONFIDENCE_REJECT_THRESHOLD,
        review_threshold: float = INSIGHT_CONFIDENCE_REVIEW_THRESHOLD,
        generic_patterns: tuple[str, ...] = GENERIC_INSIGHT_FILTER_PATTERNS,
    ) -> None:
        """Initialize confidence governance thresholds and phrase filters."""

        if not 0 <= reject_threshold < review_threshold <= 1:
            raise ValueError(
                "reject_threshold and review_threshold must satisfy "
                "0 <= reject < review <= 1."
            )
        self._reject_threshold = reject_threshold
        self._review_threshold = review_threshold
        self._generic_patterns = generic_patterns

    def apply(self, insights: list[Any]) -> InsightGovernanceResult:
        """Classify insights into export, review, and reject buckets."""

        return InsightGovernanceResult(
            decisions=[self._decision(insight) for insight in insights],
        )

    def write_audit(
        self,
        result: InsightGovernanceResult,
        output_file_path: str | Path,
    ) -> None:
        """Write the confidence filtering audit report to JSON."""

        output_path = Path(output_file_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(
            json.dumps(result.to_audit_payload(), indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

    def _decision(self, insight: Any) -> InsightGovernanceDecision:
        text = f"{insight.area} {insight.takeaway}"
        matched_generic_patterns = _matched_generic_patterns(
            text,
            self._generic_patterns,
        )
        has_quantitative_evidence = _has_quantitative_evidence(text)

        if (
            insight.confidence < self._review_threshold
            and matched_generic_patterns
            and not has_quantitative_evidence
        ):
            return InsightGovernanceDecision(
                insight=insight,
                route=INSIGHT_ROUTE_REJECT,
                reason="generic_low_confidence_without_quantitative_evidence",
                has_quantitative_evidence=False,
                matched_generic_patterns=matched_generic_patterns,
            )

        if insight.confidence < self._reject_threshold:
            if has_quantitative_evidence:
                return InsightGovernanceDecision(
                    insight=insight,
                    route=INSIGHT_ROUTE_REVIEW,
                    reason="low_confidence_quantified_safety_review",
                    has_quantitative_evidence=True,
                    matched_generic_patterns=matched_generic_patterns,
                )
            return InsightGovernanceDecision(
                insight=insight,
                route=INSIGHT_ROUTE_REJECT,
                reason="confidence_below_reject_threshold",
                has_quantitative_evidence=False,
                matched_generic_patterns=matched_generic_patterns,
            )

        if insight.confidence < self._review_threshold:
            return InsightGovernanceDecision(
                insight=insight,
                route=INSIGHT_ROUTE_REVIEW,
                reason="confidence_review_bucket",
                has_quantitative_evidence=has_quantitative_evidence,
                matched_generic_patterns=matched_generic_patterns,
            )

        return InsightGovernanceDecision(
            insight=insight,
            route=INSIGHT_ROUTE_EXPORT,
            reason="confidence_export_bucket",
            has_quantitative_evidence=has_quantitative_evidence,
            matched_generic_patterns=matched_generic_patterns,
        )


def _decision_payload(decision: InsightGovernanceDecision) -> dict[str, object]:
    insight = decision.insight
    return {
        "area": insight.area,
        "takeaway": insight.takeaway,
        "source_section": insight.source_section,
        "page_number": insight.page_number,
        "confidence": insight.confidence,
        "route": decision.route,
        "reason": decision.reason,
        "has_quantitative_evidence": decision.has_quantitative_evidence,
        "matched_generic_patterns": list(decision.matched_generic_patterns),
    }


def _confidence_bucket(confidence: float) -> str:
    if confidence == 0:
        return "0.0"
    if 0.1 <= confidence < 0.5:
        return "0.1-0.5"
    if 0.5 <= confidence < 0.7:
        return "0.5-0.7"
    if confidence >= 0.9:
        return "0.9+"
    if confidence >= 0.7:
        return "0.7-0.9"
    return "0.1-0.5"


def _matched_generic_patterns(
    text: str,
    patterns: tuple[str, ...],
) -> tuple[str, ...]:
    normalized_text = _normalize_text(text)
    return tuple(
        pattern
        for pattern in patterns
        if _normalize_text(pattern) in normalized_text
    )


def _has_quantitative_evidence(text: str) -> bool:
    normalized_text = _normalize_text(text)
    has_number = bool(re.search(r"\d", text))
    if not has_number:
        return False

    if re.search(r"(?:rs\.?|pkr|usd|\$)\s*\d", text, flags=re.IGNORECASE):
        return True
    if re.search(r"\d[\d,]*(?:\.\d+)?\s*%", text):
        return True
    return any(
        _normalize_text(term) in normalized_text
        for term in QUANTITATIVE_EVIDENCE_TERMS
    )


def _normalize_text(value: str) -> str:
    normalized = value.lower().replace("&", " and ")
    normalized = re.sub(r"[^a-z0-9%$]+", " ", normalized)
    normalized = re.sub(r"\s+", " ", normalized)
    return normalized.strip()


__all__ = [
    "INSIGHT_ROUTE_EXPORT",
    "INSIGHT_ROUTE_REJECT",
    "INSIGHT_ROUTE_REVIEW",
    "InsightConfidenceGovernance",
    "InsightGovernanceDecision",
    "InsightGovernanceResult",
]
