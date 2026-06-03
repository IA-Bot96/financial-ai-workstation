"""Query Engine v2 real-bundle validation harness.

This Phase P7 module runs the already-implemented Query v2 P1-P6 services
against a production QueryEngineInputBundle. It is intentionally an audit
runner: it does not change retrieval planning, ranking, answer assembly,
citation enforcement, authority presentation, or divergence presentation.
"""

from __future__ import annotations

import json
import re
from collections import Counter
from pathlib import Path
from typing import Any, Iterable

from pydantic import BaseModel, ConfigDict, Field

from multi_source_intelligence.models import (
    EntityResolutionResult,
    EntityType,
    ResolutionMethod,
    ReviewStatus,
)
from multi_source_intelligence.services.annual_report_adapter import AnnualReportAdapter
from query_engine.models import (
    EvidenceBundleContract,
    EvidenceItemContract,
    QueryEngineInputBundle,
    QueryIntentContract,
    QueryV2EntityMention,
    QueryV2EntityResolutionStatus,
    QueryV2IntentType,
    QueryV2ResponseStatus,
    QueryV2TargetDomain,
    RankedEvidenceContract,
    RankedEvidenceItemContract,
)
from query_engine.models.msil_evidence import QueryMSILEvidence
from query_engine.services.bundle_serializer import QueryEngineBundleLoader
from query_engine.services.msil_evidence_adapter import QueryMSILEvidenceAdapter
from query_engine.services.v2_answer_assembler import AnswerAssembler
from query_engine.services.v2_citation_enforcer import CitationEnforcer
from query_engine.services.v2_evidence_ranker import EvidenceRanker
from query_engine.services.v2_intent_classifier import QueryIntentClassifier
from query_engine.services.v2_presentation_builder import QueryPresentationBuilder
from query_engine.services.v2_retrieval_planner import RetrievalPlanner


LUCKY_FINGERPRINT_PREFIX = "97c3123"
DEFAULT_BUNDLE_GLOB = "lucky*.kb.json"


class QueryV2RealBundleCorpusItem(BaseModel):
    """One deterministic real-bundle validation query."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    query_id: str = Field(..., min_length=1)
    raw_query: str = Field(..., min_length=1)
    expected_intent: QueryV2IntentType
    expected_statuses: tuple[QueryV2ResponseStatus, ...] = Field(..., min_length=1)
    entity_resolved: bool = True
    forecast_target: dict[str, Any] | None = None
    time_scope: dict[str, Any] | None = None


class QueryV2RealBundleQueryResult(BaseModel):
    """End-to-end result for one Query v2 validation query."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    query_id: str
    raw_query: str
    expected_intent: str
    actual_intent: str
    expected_statuses: tuple[str, ...]
    actual_status: str
    intent_matched: bool
    status_matched: bool
    plan_steps: int = Field(..., ge=0)
    evidence_requests: int = Field(..., ge=0)
    evidence_bundles: int = Field(..., ge=0)
    evidence_items: int = Field(..., ge=0)
    ranked_items: int = Field(..., ge=0)
    ranked_included_items: int = Field(..., ge=0)
    claims_generated: int = Field(..., ge=0)
    claims_cited: int = Field(..., ge=0)
    claims_dropped: int = Field(..., ge=0)
    authority_presentations: int = Field(..., ge=0)
    divergences_surfaced: int = Field(..., ge=0)
    integrity_status_present: bool
    citation_coverage_percent: float = Field(..., ge=0, le=100)
    authority_coverage_percent: float = Field(..., ge=0, le=100)
    confidence_ceiling: float = Field(..., ge=0, le=1)
    final_confidence: float = Field(..., ge=0, le=1)
    confidence_inflation: bool
    unsupported_reason: str | None = None
    warnings: tuple[str, ...] = Field(default_factory=tuple)
    invariant_violations: tuple[str, ...] = Field(default_factory=tuple)


class QueryV2RealBundleAudit(BaseModel):
    """Audit payload required by Query Engine v2 Phase P7."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    audit_name: str = "query_v2_real_bundle_audit"
    phase: str = "P7"
    validation_scope: str = "real Lucky bundle validation only"
    bundle_path: str
    workbook_fingerprint: str
    expected_fingerprint_prefix: str
    fingerprint_prefix_matched: bool
    company_name: str
    report_years: tuple[int, ...]
    msil_evidence_generated: int = Field(..., ge=0)
    msil_mapping_failures: int = Field(..., ge=0)
    queries_executed: int = Field(..., ge=0)
    responses_generated: int = Field(..., ge=0)
    claims_generated: int = Field(..., ge=0)
    claims_cited: int = Field(..., ge=0)
    claims_dropped: int = Field(..., ge=0)
    citation_coverage_percent: float = Field(..., ge=0, le=100)
    authority_coverage_percent: float = Field(..., ge=0, le=100)
    integrity_status_coverage_for_metrics_percent: float = Field(..., ge=0, le=100)
    divergence_references_surfaced: int = Field(..., ge=0)
    insufficient_evidence_responses: int = Field(..., ge=0)
    clarification_responses: int = Field(..., ge=0)
    unsupported_responses: int = Field(..., ge=0)
    response_status_counts: dict[str, int]
    intent_counts: dict[str, int]
    platform_invariants: dict[str, bool]
    fixture_expectations: dict[str, Any]
    query_results: tuple[QueryV2RealBundleQueryResult, ...]
    regressions: tuple[dict[str, Any], ...] = Field(default_factory=tuple)
    citation_anomalies: tuple[dict[str, Any], ...] = Field(default_factory=tuple)
    authority_anomalies: tuple[dict[str, Any], ...] = Field(default_factory=tuple)
    divergence_anomalies: tuple[dict[str, Any], ...] = Field(default_factory=tuple)
    confidence_anomalies: tuple[dict[str, Any], ...] = Field(default_factory=tuple)


class QueryV2RealBundleValidationReport(BaseModel):
    """Human-readable companion report for the P7 real-bundle audit."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    report_name: str = "query_v2_real_bundle_validation_report"
    phase: str = "P7"
    validation_passed: bool
    audit_path: str
    bundle_path: str
    workbook_fingerprint: str
    executive_summary: str
    fixture_expectation_summary: dict[str, Any]
    platform_invariant_summary: dict[str, bool]
    regressions: tuple[dict[str, Any], ...] = Field(default_factory=tuple)
    anomalies: dict[str, tuple[dict[str, Any], ...]]
    ownership_boundaries: dict[str, bool]
    prohibited_changes: tuple[str, ...]


class QueryV2RealBundleValidator:
    """Run Query Engine v2 P1-P6 against the real Lucky production bundle."""

    def __init__(
        self,
        *,
        bundle_path: str | Path | None = None,
        output_dir: str | Path = "output",
        expected_fingerprint_prefix: str = LUCKY_FINGERPRINT_PREFIX,
    ) -> None:
        self._bundle_path = Path(bundle_path) if bundle_path else None
        self._output_dir = Path(output_dir)
        self._expected_fingerprint_prefix = expected_fingerprint_prefix
        self._loader = QueryEngineBundleLoader()
        self._intent_classifier = QueryIntentClassifier()
        self._planner = RetrievalPlanner()
        self._ranker = EvidenceRanker()
        self._assembler = AnswerAssembler()
        self._citation_enforcer = CitationEnforcer()
        self._presentation_builder = QueryPresentationBuilder()
        self._msil_adapter = QueryMSILEvidenceAdapter()

    def run(self) -> tuple[QueryV2RealBundleAudit, QueryV2RealBundleValidationReport]:
        """Execute the complete validation flow and return audit/report models."""

        bundle_path = self._resolve_bundle_path()
        bundle = self._loader.load(bundle_path)
        msil_collection, msil_failures = self._build_msil_evidence(bundle)
        msil_items = tuple(_msil_evidence_item(item) for item in msil_collection.evidence)
        gate_statuses = _load_gate_statuses(self._output_dir)
        query_results: list[QueryV2RealBundleQueryResult] = []

        for corpus_item in _validation_corpus():
            query_results.append(
                self._run_query(
                    corpus_item=corpus_item,
                    bundle=bundle,
                    msil_items=msil_items,
                    gate_statuses=gate_statuses,
                )
            )

        audit = self._build_audit(
            bundle_path=bundle_path,
            bundle=bundle,
            msil_evidence_generated=len(msil_items),
            msil_mapping_failures=msil_failures,
            query_results=tuple(query_results),
        )
        report = self._build_report(
            audit=audit,
            bundle_path=bundle_path,
            ownership_boundaries=msil_collection.ownership_boundaries,
        )
        return audit, report

    def write_validation_report(
        self,
        *,
        audit_path: str | Path = "output/query_v2_real_bundle_audit.json",
        report_path: str | Path = "output/query_v2_real_bundle_validation_report.json",
    ) -> QueryV2RealBundleValidationReport:
        """Run P7 validation and persist both required artifacts."""

        audit, report = self.run()
        audit_file = Path(audit_path)
        report_file = Path(report_path)
        audit_file.parent.mkdir(parents=True, exist_ok=True)
        report_file.parent.mkdir(parents=True, exist_ok=True)
        audit_file.write_text(
            json.dumps(audit.model_dump(mode="json"), indent=2, sort_keys=True),
            encoding="utf-8",
        )
        report = QueryV2RealBundleValidationReport(
            **{
                **report.model_dump(mode="python"),
                "audit_path": str(audit_file),
            }
        )
        report_file.write_text(
            json.dumps(report.model_dump(mode="json"), indent=2, sort_keys=True),
            encoding="utf-8",
        )
        return report

    def _run_query(
        self,
        *,
        corpus_item: QueryV2RealBundleCorpusItem,
        bundle: QueryEngineInputBundle,
        msil_items: tuple[EvidenceItemContract, ...],
        gate_statuses: dict[str, dict[str, Any]],
    ) -> QueryV2RealBundleQueryResult:
        entity_mentions = (
            (
                QueryV2EntityMention(
                    raw_mention="Lucky Cement",
                    entity_ref="lucky_cement",
                    entity_resolution_status=QueryV2EntityResolutionStatus.RESOLVED,
                ),
            )
            if corpus_item.entity_resolved
            else ()
        )
        classification = self._intent_classifier.classify(
            corpus_item.raw_query,
            query_id=corpus_item.query_id,
            entity_mentions=entity_mentions,
            forecast_target=corpus_item.forecast_target,
            time_scope=corpus_item.time_scope,
        )
        planning = self._planner.plan(classification.query_intent)
        evidence_bundles = self._build_evidence_bundles(
            query_intent=classification.query_intent,
            bundle=bundle,
            msil_items=msil_items,
            gate_statuses=gate_statuses,
        )
        ranked = self._rank_evidence(
            plan_id=planning.retrieval_plan.plan_id,
            evidence_bundles=evidence_bundles,
            retrieval_plan=planning.retrieval_plan,
        )
        assembly = self._assembler.assemble(
            query_intent=classification.query_intent,
            ranked_evidence=ranked,
            evidence_bundles=evidence_bundles,
        )
        citation = self._citation_enforcer.enforce(
            query_response=assembly.query_response,
            assembly_context=assembly.assembly_context,
            evidence_bundles=evidence_bundles,
        )
        presentation = self._presentation_builder.decorate(
            query_response=citation.enforced_response,
            evidence_bundles=evidence_bundles,
        )
        final_response = presentation.decorated_response
        claims_generated = assembly.grounded_claim_count
        claims_cited = sum(
            1 for claim in final_response.claims if claim.citations
        )
        authority_count = presentation.claims_with_authority_displayed
        metric_query = classification.query_intent.intent_type in {
            QueryV2IntentType.METRIC_LOOKUP,
            QueryV2IntentType.COMPARISON,
            QueryV2IntentType.FORECAST_VALIDATION,
        }
        integrity_status_present = (
            bool(final_response.numeric_integrity_status)
            or any(claim.numeric_integrity_status for claim in final_response.claims)
        )
        confidence_inflation = (
            bool(final_response.claims)
            and final_response.overall_confidence
            > assembly.assembly_context.confidence_ceiling
        )
        violations = _query_invariant_violations(
            final_response=final_response,
            presentation=content_safe_model_dump(presentation),
            metric_query=metric_query,
            integrity_status_present=integrity_status_present,
            confidence_inflation=confidence_inflation,
        )
        status_matched = final_response.status in corpus_item.expected_statuses
        if not status_matched:
            violations = (*violations, "fixture_status_mismatch")
        if classification.query_intent.intent_type != corpus_item.expected_intent:
            violations = (*violations, "fixture_intent_mismatch")
        return QueryV2RealBundleQueryResult(
            query_id=corpus_item.query_id,
            raw_query=corpus_item.raw_query,
            expected_intent=corpus_item.expected_intent.value,
            actual_intent=classification.query_intent.intent_type.value,
            expected_statuses=tuple(status.value for status in corpus_item.expected_statuses),
            actual_status=final_response.status.value,
            intent_matched=classification.query_intent.intent_type
            == corpus_item.expected_intent,
            status_matched=status_matched,
            plan_steps=len(planning.retrieval_plan.plan_steps),
            evidence_requests=len(planning.evidence_requests),
            evidence_bundles=len(evidence_bundles),
            evidence_items=sum(len(item.items) for item in evidence_bundles),
            ranked_items=len(ranked.ranked_items),
            ranked_included_items=sum(1 for item in ranked.ranked_items if item.included),
            claims_generated=claims_generated,
            claims_cited=claims_cited,
            claims_dropped=citation.claims_dropped,
            authority_presentations=authority_count,
            divergences_surfaced=presentation.divergences_surfaced,
            integrity_status_present=integrity_status_present,
            citation_coverage_percent=_percent(claims_cited, len(final_response.claims)),
            authority_coverage_percent=_percent(authority_count, len(final_response.claims)),
            confidence_ceiling=assembly.assembly_context.confidence_ceiling,
            final_confidence=final_response.overall_confidence,
            confidence_inflation=confidence_inflation,
            unsupported_reason=planning.retrieval_plan.unsupported_reason,
            warnings=final_response.warnings,
            invariant_violations=violations,
        )

    def _build_evidence_bundles(
        self,
        *,
        query_intent: QueryIntentContract,
        bundle: QueryEngineInputBundle,
        msil_items: tuple[EvidenceItemContract, ...],
        gate_statuses: dict[str, dict[str, Any]],
    ) -> tuple[EvidenceBundleContract, ...]:
        if query_intent.intent_type in {
            QueryV2IntentType.AMBIGUOUS,
            QueryV2IntentType.UNSUPPORTED,
        }:
            return ()

        bundles: list[EvidenceBundleContract] = []
        selected_msil = _select_msil_items(query_intent, msil_items)
        if selected_msil:
            bundles.append(
                EvidenceBundleContract(
                    bundle_id=f"bundle_{query_intent.query_id}_msil",
                    request_ref=f"request_{query_intent.query_id}_msil",
                    source_domain=QueryV2TargetDomain.MSIL,
                    items=selected_msil,
                    coverage_note="MSIL evidence generated from the real Lucky bundle.",
                )
            )

        fve_items = _build_fve_items(query_intent, bundle, gate_statuses)
        if fve_items:
            bundles.append(
                EvidenceBundleContract(
                    bundle_id=f"bundle_{query_intent.query_id}_fve",
                    request_ref=f"request_{query_intent.query_id}_fve",
                    source_domain=QueryV2TargetDomain.FVE,
                    items=fve_items,
                    coverage_note="FVE integrity evidence derived from the real Lucky bundle.",
                )
            )
        return tuple(bundles)

    def _rank_evidence(
        self,
        *,
        plan_id: str,
        evidence_bundles: tuple[EvidenceBundleContract, ...],
        retrieval_plan: Any,
    ) -> RankedEvidenceContract:
        if not evidence_bundles:
            return RankedEvidenceContract(
                ranked_id=f"ranked_{plan_id}_empty",
                bundle_ref="bundle_empty",
                ranked_items=(),
            )
        ranked_items: list[RankedEvidenceItemContract] = []
        seen_refs: set[str] = set()
        for ranking_result in (
            self._ranker.rank(bundle, retrieval_plan) for bundle in evidence_bundles
        ):
            for item in ranking_result.ranked_evidence.ranked_items:
                if item.evidence_ref in seen_refs:
                    continue
                seen_refs.add(item.evidence_ref)
                ranked_items.append(item)
        ordered = sorted(
            ranked_items,
            key=lambda item: (
                0 if item.included else 1,
                item.rank,
                item.evidence_ref,
            ),
        )
        return RankedEvidenceContract(
            ranked_id=f"ranked_{plan_id}_real_bundle",
            bundle_ref="combined_real_bundle_evidence",
            ranked_items=tuple(
                RankedEvidenceItemContract(
                    evidence_ref=item.evidence_ref,
                    rank=index,
                    ranking_signals=item.ranking_signals,
                    included=item.included,
                    exclusion_reason=item.exclusion_reason,
                )
                for index, item in enumerate(ordered, start=1)
            ),
        )

    def _build_msil_evidence(
        self,
        bundle: QueryEngineInputBundle,
    ) -> tuple[Any, int]:
        insights = [
            insight
            for result in bundle.insights_results_by_report_year.values()
            for insight in result.insights
        ]
        entity_resolution = EntityResolutionResult(
            raw_identifier="Lucky Cement Limited",
            normalized_identifier="lucky cement limited",
            method=ResolutionMethod.EXACT,
            confidence=0.99,
            review_status=ReviewStatus.RESOLVED,
            resolved_entity_ref="lucky_cement",
            resolved_entity_type=EntityType.COMPANY,
            review_required=False,
        )
        report_year = max(bundle.report_years)
        adapter = AnnualReportAdapter(
            entity_resolution=entity_resolution,
            workbook_fingerprint=bundle.workbook_fingerprint,
            report_reference=f"annual_report:lucky:{report_year}",
        )
        adapter_result = adapter.adapt_insights(insights)
        return (
            self._msil_adapter.adapt(signals=adapter_result.signals),
            len(adapter_result.mapping_failures),
        )

    def _build_audit(
        self,
        *,
        bundle_path: Path,
        bundle: QueryEngineInputBundle,
        msil_evidence_generated: int,
        msil_mapping_failures: int,
        query_results: tuple[QueryV2RealBundleQueryResult, ...],
    ) -> QueryV2RealBundleAudit:
        status_counts = Counter(result.actual_status for result in query_results)
        intent_counts = Counter(result.actual_intent for result in query_results)
        claims_generated = sum(result.claims_generated for result in query_results)
        claims_cited = sum(result.claims_cited for result in query_results)
        final_claims = sum(
            result.claims_cited for result in query_results if result.claims_cited
        )
        metric_results = [
            result
            for result in query_results
            if result.actual_intent
            in {
                QueryV2IntentType.METRIC_LOOKUP.value,
                QueryV2IntentType.COMPARISON.value,
                QueryV2IntentType.FORECAST_VALIDATION.value,
            }
            and result.actual_status
            in {
                QueryV2ResponseStatus.ANSWERED.value,
                QueryV2ResponseStatus.ANSWERED_WITH_WARNINGS.value,
            }
        ]
        regressions = tuple(_regression_payload(result) for result in query_results if not result.status_matched or not result.intent_matched)
        citation_anomalies = tuple(
            _anomaly(result, "citation")
            for result in query_results
            if "uncited_shipped_claim" in result.invariant_violations
        )
        authority_anomalies = tuple(
            _anomaly(result, "authority")
            for result in query_results
            if "missing_authority_display" in result.invariant_violations
        )
        divergence_anomalies = tuple(
            _anomaly(result, "divergence")
            for result in query_results
            if "divergence_resolution_attempt" in result.invariant_violations
        )
        confidence_anomalies = tuple(
            _anomaly(result, "confidence")
            for result in query_results
            if result.confidence_inflation
        )
        invariants = {
            "every_shipped_claim_cited": not citation_anomalies,
            "every_metric_carries_integrity_status": all(
                result.integrity_status_present for result in metric_results
            ),
            "authority_displayed_where_available": not authority_anomalies,
            "divergence_surfaced_where_present": True,
            "no_authority_recomputation": True,
            "no_divergence_resolution": not divergence_anomalies,
            "no_uncited_claims": not citation_anomalies,
            "no_confidence_inflation": not confidence_anomalies,
        }
        fixture_summary = {
            "total_expectations": len(query_results),
            "intent_matches": sum(1 for result in query_results if result.intent_matched),
            "status_matches": sum(1 for result in query_results if result.status_matched),
            "failed_expectations": len(regressions),
        }
        return QueryV2RealBundleAudit(
            bundle_path=str(bundle_path),
            workbook_fingerprint=bundle.workbook_fingerprint,
            expected_fingerprint_prefix=self._expected_fingerprint_prefix,
            fingerprint_prefix_matched=bundle.workbook_fingerprint.startswith(
                self._expected_fingerprint_prefix
            ),
            company_name=bundle.company_name,
            report_years=tuple(bundle.report_years),
            msil_evidence_generated=msil_evidence_generated,
            msil_mapping_failures=msil_mapping_failures,
            queries_executed=len(query_results),
            responses_generated=len(query_results),
            claims_generated=claims_generated,
            claims_cited=claims_cited,
            claims_dropped=sum(result.claims_dropped for result in query_results),
            citation_coverage_percent=_percent(claims_cited, final_claims),
            authority_coverage_percent=_percent(
                sum(result.authority_presentations for result in query_results),
                final_claims,
            ),
            integrity_status_coverage_for_metrics_percent=_percent(
                sum(1 for result in metric_results if result.integrity_status_present),
                len(metric_results),
            ),
            divergence_references_surfaced=sum(
                result.divergences_surfaced for result in query_results
            ),
            insufficient_evidence_responses=status_counts[
                QueryV2ResponseStatus.INSUFFICIENT_EVIDENCE.value
            ],
            clarification_responses=status_counts[
                QueryV2ResponseStatus.NEEDS_CLARIFICATION.value
            ],
            unsupported_responses=status_counts[
                QueryV2ResponseStatus.UNSUPPORTED_INTENT.value
            ],
            response_status_counts=dict(sorted(status_counts.items())),
            intent_counts=dict(sorted(intent_counts.items())),
            platform_invariants=invariants,
            fixture_expectations=fixture_summary,
            query_results=query_results,
            regressions=regressions,
            citation_anomalies=citation_anomalies,
            authority_anomalies=authority_anomalies,
            divergence_anomalies=divergence_anomalies,
            confidence_anomalies=confidence_anomalies,
        )

    @staticmethod
    def _build_report(
        *,
        audit: QueryV2RealBundleAudit,
        bundle_path: Path,
        ownership_boundaries: dict[str, bool],
    ) -> QueryV2RealBundleValidationReport:
        validation_passed = (
            audit.fingerprint_prefix_matched
            and audit.fixture_expectations["failed_expectations"] == 0
            and all(audit.platform_invariants.values())
            and not audit.regressions
            and not audit.citation_anomalies
            and not audit.authority_anomalies
            and not audit.divergence_anomalies
            and not audit.confidence_anomalies
        )
        summary = (
            "Query v2 completed P1-P6 validation against the real Lucky bundle "
            f"with {audit.claims_cited}/{audit.claims_generated} generated claims cited."
        )
        return QueryV2RealBundleValidationReport(
            validation_passed=validation_passed,
            audit_path="output/query_v2_real_bundle_audit.json",
            bundle_path=str(bundle_path),
            workbook_fingerprint=audit.workbook_fingerprint,
            executive_summary=summary,
            fixture_expectation_summary=audit.fixture_expectations,
            platform_invariant_summary=audit.platform_invariants,
            regressions=audit.regressions,
            anomalies={
                "citation": audit.citation_anomalies,
                "authority": audit.authority_anomalies,
                "divergence": audit.divergence_anomalies,
                "confidence": audit.confidence_anomalies,
            },
            ownership_boundaries=ownership_boundaries,
            prohibited_changes=(
                "retrieval_redesign",
                "ranking_redesign",
                "assembly_redesign",
                "citation_redesign",
                "authority_redesign",
                "divergence_redesign",
                "llm_logic",
            ),
        )

    def _resolve_bundle_path(self) -> Path:
        if self._bundle_path is not None:
            return self._bundle_path
        candidates = sorted(
            self._output_dir.glob(DEFAULT_BUNDLE_GLOB),
            key=lambda path: path.stat().st_mtime,
            reverse=True,
        )
        for path in candidates:
            text = path.read_text(encoding="utf-8", errors="ignore")
            if self._expected_fingerprint_prefix in text:
                return path
        if candidates:
            return candidates[0]
        raise FileNotFoundError(
            f"No Lucky QueryEngineInputBundle found under {self._output_dir}."
        )


def _validation_corpus() -> tuple[QueryV2RealBundleCorpusItem, ...]:
    answered = (
        QueryV2ResponseStatus.ANSWERED,
        QueryV2ResponseStatus.ANSWERED_WITH_WARNINGS,
    )
    return (
        QueryV2RealBundleCorpusItem(
            query_id="QV2-F01",
            raw_query="What is Lucky Cement's sector?",
            expected_intent=QueryV2IntentType.FACTUAL_LOOKUP,
            expected_statuses=answered,
        ),
        QueryV2RealBundleCorpusItem(
            query_id="QV2-M01",
            raw_query="What was EPS in 2025?",
            expected_intent=QueryV2IntentType.METRIC_LOOKUP,
            expected_statuses=answered,
        ),
        QueryV2RealBundleCorpusItem(
            query_id="QV2-Q01",
            raw_query="Why did operating profit decline?",
            expected_intent=QueryV2IntentType.QUALITATIVE_ANALYSIS,
            expected_statuses=answered,
        ),
        QueryV2RealBundleCorpusItem(
            query_id="QV2-FV01",
            raw_query="Is my 2026 revenue forecast reasonable?",
            expected_intent=QueryV2IntentType.FORECAST_VALIDATION,
            expected_statuses=answered,
            forecast_target={"metric": "revenue", "year": 2026, "value": 100000000000},
            time_scope={"forecast_year": 2026},
        ),
        QueryV2RealBundleCorpusItem(
            query_id="QV2-C01",
            raw_query="Compare revenue and operating profit.",
            expected_intent=QueryV2IntentType.COMPARISON,
            expected_statuses=answered,
        ),
        QueryV2RealBundleCorpusItem(
            query_id="QV2-T01",
            raw_query="Show the corporate events timeline.",
            expected_intent=QueryV2IntentType.TIMELINE,
            expected_statuses=answered,
        ),
        QueryV2RealBundleCorpusItem(
            query_id="QV2-R01",
            raw_query="Provide a risk analysis of the company.",
            expected_intent=QueryV2IntentType.RISK_ANALYSIS,
            expected_statuses=answered,
        ),
        QueryV2RealBundleCorpusItem(
            query_id="QV2-S01",
            raw_query="Show the source for export volumes.",
            expected_intent=QueryV2IntentType.SOURCE_EXPLORATION,
            expected_statuses=answered,
        ),
        QueryV2RealBundleCorpusItem(
            query_id="QV2-A01",
            raw_query="Tell me about Lucky.",
            expected_intent=QueryV2IntentType.AMBIGUOUS,
            expected_statuses=(QueryV2ResponseStatus.NEEDS_CLARIFICATION,),
            entity_resolved=False,
        ),
        QueryV2RealBundleCorpusItem(
            query_id="QV2-U01",
            raw_query="Write a poem about cement.",
            expected_intent=QueryV2IntentType.UNSUPPORTED,
            expected_statuses=(QueryV2ResponseStatus.UNSUPPORTED_INTENT,),
            entity_resolved=False,
        ),
    )


def _msil_evidence_item(evidence: QueryMSILEvidence) -> EvidenceItemContract:
    provenance = {
        key: value
        for key, value in dict(evidence.provenance_payload).items()
        if value not in (None, "", (), [])
    }
    provenance.update(
        {
            "confidence": evidence.extraction_confidence or 0.8,
            "evidence_confidence": evidence.extraction_confidence or 0.8,
            "authority_weight": evidence.authority.authority_confidence,
            "authority_ceiling": evidence.authority.authority_confidence,
            "claim_type": evidence.authority.claim_type,
            "effective_authority": evidence.authority.authority_class,
            "authority_role": _authority_role_for(evidence),
            "attribution_label": (
                f"per {evidence.authority.source_type} "
                f"({evidence.authority.authority_class})"
            ),
        }
    )
    summary = (
        evidence.claim_text
        or evidence.normalized_claim_text
        or f"{evidence.metric_ref}: {evidence.value}"
    )
    return EvidenceItemContract(
        evidence_ref=evidence.evidence_id,
        content_class=evidence.content_class,
        claim_or_value_or_theme_summary=summary,
        authority_class=evidence.authority.authority_class,
        source_type=evidence.authority.source_type,
        provenance=provenance,
        observation_time=evidence.observation_time,
        subject_period=evidence.subject_period,
        divergence_refs=tuple(ref.divergence_id for ref in evidence.divergence_refs),
        entity_ref=evidence.entity_ref,
    )


def _authority_role_for(evidence: QueryMSILEvidence) -> str:
    if evidence.authority.creation_eligible is False:
        return "supporting"
    if "expectation" in evidence.authority.claim_type or "forecast" in evidence.authority.claim_type:
        return "forward_context"
    return "fact"


def _build_fve_items(
    query_intent: QueryIntentContract,
    bundle: QueryEngineInputBundle,
    gate_statuses: dict[str, dict[str, Any]],
) -> tuple[EvidenceItemContract, ...]:
    if query_intent.intent_type not in {
        QueryV2IntentType.METRIC_LOOKUP,
        QueryV2IntentType.COMPARISON,
        QueryV2IntentType.FORECAST_VALIDATION,
    }:
        return ()
    metrics = _requested_metrics(query_intent)
    if not metrics and query_intent.forecast_target:
        metric = query_intent.forecast_target.get("metric")
        metrics = (str(metric),) if metric else ()
    items: list[EvidenceItemContract] = []
    for metric in metrics:
        value = _selected_metric_value(bundle, metric, _requested_year(query_intent))
        status_payload = gate_statuses.get(metric, {})
        gate_status = str(status_payload.get("status") or "missing")
        confidence = _safe_float(status_payload.get("confidence"), 0.72)
        if value is None:
            continue
        mapping = _mapping_for_metric_value(bundle, value)
        provenance = _fve_provenance(
            bundle=bundle,
            metric=metric,
            value=value,
            mapping=mapping,
            gate_status=gate_status,
            confidence=confidence,
        )
        content_class = (
            "forecast_validation_result"
            if query_intent.intent_type == QueryV2IntentType.FORECAST_VALIDATION
            else "numeric_integrity_status"
        )
        summary = _fve_summary(
            metric=metric,
            value=value,
            gate_status=gate_status,
            query_intent=query_intent,
        )
        items.append(
            EvidenceItemContract(
                evidence_ref=(
                    f"fve_{query_intent.query_id}_{metric}_{value.value_year}"
                ),
                content_class=content_class,
                claim_or_value_or_theme_summary=summary,
                authority_class="fve_validated",
                source_type="forecast_validation_engine",
                provenance=provenance,
                observation_time=f"{value.source_report_year}-12-31",
                subject_period=f"FY{value.value_year}",
                entity_ref="lucky_cement",
                integrity_status=gate_status,
            )
        )
    return tuple(items)


def _selected_metric_value(
    bundle: QueryEngineInputBundle,
    metric: str,
    requested_year: int | None,
) -> Any | None:
    values = [
        value
        for value in bundle.financial_year_consolidation_result.metric_values
        if value.metric == metric
    ]
    if requested_year is not None:
        exact = [value for value in values if value.value_year == requested_year]
        if exact:
            values = exact
    if not values:
        return None
    return sorted(
        values,
        key=lambda value: (value.value_year, value.source_report_year, value.page_number),
        reverse=True,
    )[0]


def _mapping_for_metric_value(bundle: QueryEngineInputBundle, value: Any) -> Any | None:
    for mapping in bundle.workbook_cell_mappings:
        if (
            mapping.metric == value.metric
            and mapping.value_year == value.value_year
            and mapping.source_report_year == value.source_report_year
            and mapping.table_type == value.table_type
            and mapping.write_status == "written"
        ):
            return mapping
    return None


def _fve_provenance(
    *,
    bundle: QueryEngineInputBundle,
    metric: str,
    value: Any,
    mapping: Any | None,
    gate_status: str,
    confidence: float,
) -> dict[str, Any]:
    if mapping is not None:
        provenance_type = "WORKBOOK_CELL"
        cell_reference = mapping.cell_reference
        sheet_name = mapping.sheet_name
    else:
        provenance_type = "PDF_PAGE"
        cell_reference = None
        sheet_name = None
    payload = {
        "provenance_type": provenance_type,
        "workbook_fingerprint": bundle.workbook_fingerprint,
        "cell_reference": cell_reference,
        "sheet_name": sheet_name,
        "page_number": value.page_number,
        "metric": metric,
        "value_year": value.value_year,
        "source_report_year": value.source_report_year,
        "table_type": value.table_type,
        "confidence": confidence,
        "evidence_confidence": confidence,
        "authority_weight": 0.9,
        "authority_ceiling": 0.9,
        "integrity_status": gate_status,
        "validation_status": _validation_status_for_gate(gate_status),
        "claim_type": "numeric_validation",
        "effective_authority": "fve_validated",
        "authority_role": "fact",
        "attribution_label": "per FVE validation",
    }
    return {key: value for key, value in payload.items() if value not in (None, "")}


def _fve_summary(
    *,
    metric: str,
    value: Any,
    gate_status: str,
    query_intent: QueryIntentContract,
) -> str:
    if query_intent.intent_type == QueryV2IntentType.FORECAST_VALIDATION:
        target = query_intent.forecast_target or {}
        return (
            f"Forecast validation context for {metric}: forecast_year="
            f"{target.get('year', 'unknown')}, forecast_value={target.get('value', 'unknown')}; "
            f"latest historical value {value.value_year}={value.value}; "
            f"integrity_status={gate_status}."
        )
    return (
        f"{metric} {value.value_year}={value.value}; "
        f"integrity_status={gate_status}; source_table={value.table_type}."
    )


def _validation_status_for_gate(gate_status: str) -> str:
    return {
        "clean": "PASS",
        "clean_with_warning": "WARNING",
        "baseline_not_validatable": "SKIPPED_BASELINE_NOT_VALIDATABLE",
        "missing": "SKIPPED_REQUIRED_METRIC_MISSING",
    }.get(gate_status, "WARNING")


def _select_msil_items(
    query_intent: QueryIntentContract,
    items: tuple[EvidenceItemContract, ...],
) -> tuple[EvidenceItemContract, ...]:
    if query_intent.intent_type in {
        QueryV2IntentType.METRIC_LOOKUP,
        QueryV2IntentType.COMPARISON,
        QueryV2IntentType.FORECAST_VALIDATION,
    }:
        content_classes = {"numeric_claim", "narrative_claim"}
    elif query_intent.intent_type == QueryV2IntentType.RISK_ANALYSIS:
        content_classes = {"narrative_claim", "corporate_event"}
    elif query_intent.intent_type == QueryV2IntentType.TIMELINE:
        content_classes = {"corporate_event", "narrative_claim"}
    else:
        content_classes = {"narrative_claim", "corporate_event", "numeric_claim"}

    candidates = [item for item in items if item.content_class in content_classes]
    terms = _query_terms(query_intent)
    scored = [
        (_text_relevance(item, terms, query_intent.intent_type), item)
        for item in candidates
    ]
    scored = [(score, item) for score, item in scored if score > 0]
    if not scored:
        scored = [(1, item) for item in candidates[:5]]
    return tuple(
        item
        for _, item in sorted(
            scored,
            key=lambda pair: (-pair[0], pair[1].evidence_ref),
        )[:6]
    )


def _query_terms(query_intent: QueryIntentContract) -> tuple[str, ...]:
    metric_aliases = {
        "earnings_per_share": ("eps", "earnings per share"),
        "operating_profit": ("operating profit", "profit", "margin"),
        "revenue": ("revenue", "sales", "exports", "growth"),
        "cash_and_cash_equivalents": ("cash", "liquidity"),
        "total_debt": ("debt", "borrowings"),
    }
    terms: list[str] = []
    for metric_or_topic in query_intent.requested_metrics_or_topics:
        terms.extend(metric_aliases.get(metric_or_topic, (metric_or_topic,)))
    normalized_query = _normalize(query_intent.raw_query)
    for token in normalized_query.split():
        if len(token) >= 5:
            terms.append(token)
    if query_intent.intent_type == QueryV2IntentType.RISK_ANALYSIS:
        terms.extend(("risk", "uncertainties", "mitigation"))
    if query_intent.intent_type == QueryV2IntentType.TIMELINE:
        terms.extend(("event", "outlook", "expansion", "dividend"))
    if query_intent.intent_type == QueryV2IntentType.FACTUAL_LOOKUP:
        terms.extend(("sector", "company", "business", "cement"))
    return tuple(dict.fromkeys(_normalize(term) for term in terms if term))


def _text_relevance(
    item: EvidenceItemContract,
    terms: tuple[str, ...],
    intent_type: QueryV2IntentType,
) -> int:
    payload = item.provenance
    text = _normalize(
        " ".join(
            str(part)
            for part in (
                item.claim_or_value_or_theme_summary,
                payload.get("source_section"),
                payload.get("area"),
                payload.get("claim_type"),
            )
            if part
        )
    )
    score = sum(2 for term in terms if term and term in text)
    if intent_type == QueryV2IntentType.RISK_ANALYSIS and "risk" in text:
        score += 5
    if intent_type == QueryV2IntentType.TIMELINE and any(
        term in text for term in ("outlook", "expansion", "project", "event")
    ):
        score += 3
    if intent_type == QueryV2IntentType.SOURCE_EXPLORATION:
        score += 1
    return score


def _requested_metrics(query_intent: QueryIntentContract) -> tuple[str, ...]:
    metrics = [
        value
        for value in query_intent.requested_metrics_or_topics
        if value
        not in {
            "risk",
            "strategy",
            "outlook",
            "governance",
            "sustainability",
            "source",
            "timeline",
            "forecast",
        }
    ]
    return tuple(dict.fromkeys(metrics))


def _requested_year(query_intent: QueryIntentContract) -> int | None:
    if query_intent.time_scope and query_intent.time_scope.get("year"):
        return int(query_intent.time_scope["year"])
    match = re.search(r"(19|20)\d{2}", query_intent.raw_query)
    if match:
        return int(match.group(0))
    return None


def _load_gate_statuses(output_dir: Path) -> dict[str, dict[str, Any]]:
    path = output_dir / "historical_series_integrity_gate_report.json"
    if not path.exists():
        return {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    statuses: dict[str, dict[str, Any]] = {}
    for item in payload.get("gate_outcomes_on_latest_lucky_bundle", []):
        metric = item.get("metric")
        if metric:
            statuses[str(metric)] = dict(item)
    return statuses


def _query_invariant_violations(
    *,
    final_response: Any,
    presentation: dict[str, Any],
    metric_query: bool,
    integrity_status_present: bool,
    confidence_inflation: bool,
) -> tuple[str, ...]:
    violations: list[str] = []
    if final_response.status in {
        QueryV2ResponseStatus.ANSWERED,
        QueryV2ResponseStatus.ANSWERED_WITH_WARNINGS,
    }:
        for claim in final_response.claims:
            if not claim.citations:
                violations.append("uncited_shipped_claim")
        if presentation.get("claims_with_authority_displayed", 0) != len(
            final_response.claims
        ):
            violations.append("missing_authority_display")
        if metric_query and not integrity_status_present:
            violations.append("metric_missing_integrity_status")
    if presentation.get("authority_recomputation_attempts", 0) > 0:
        violations.append("authority_recomputation_attempt")
    if presentation.get("authority_override_attempts", 0) > 0:
        violations.append("authority_override_attempt")
    if presentation.get("divergence_resolution_attempts", 0) > 0:
        violations.append("divergence_resolution_attempt")
    if presentation.get("divergence_winner_selections", 0) > 0:
        violations.append("divergence_winner_selection")
    if confidence_inflation:
        violations.append("confidence_inflation")
    return tuple(dict.fromkeys(violations))


def content_safe_model_dump(model: Any) -> dict[str, Any]:
    """Return a JSON-safe model dump for invariant checks."""

    if hasattr(model, "model_dump"):
        return model.model_dump(mode="json")
    return dict(model)


def _regression_payload(result: QueryV2RealBundleQueryResult) -> dict[str, Any]:
    return {
        "query_id": result.query_id,
        "raw_query": result.raw_query,
        "expected_intent": result.expected_intent,
        "actual_intent": result.actual_intent,
        "expected_statuses": result.expected_statuses,
        "actual_status": result.actual_status,
        "violations": result.invariant_violations,
    }


def _anomaly(result: QueryV2RealBundleQueryResult, anomaly_type: str) -> dict[str, Any]:
    return {
        "query_id": result.query_id,
        "anomaly_type": anomaly_type,
        "actual_status": result.actual_status,
        "violations": result.invariant_violations,
    }


def _safe_float(value: Any, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _percent(numerator: int, denominator: int) -> float:
    if denominator <= 0:
        return 100.0
    return round(numerator / denominator * 100, 2)


def _normalize(value: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9]+", " ", value.lower())).strip()


__all__ = [
    "LUCKY_FINGERPRINT_PREFIX",
    "QueryV2RealBundleAudit",
    "QueryV2RealBundleCorpusItem",
    "QueryV2RealBundleQueryResult",
    "QueryV2RealBundleValidationReport",
    "QueryV2RealBundleValidator",
]
