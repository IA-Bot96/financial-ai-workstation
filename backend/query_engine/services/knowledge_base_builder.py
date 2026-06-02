"""Build immutable CompanyKnowledgeBase instances from Phase 0 bundles."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from query_engine.models.input_bundle import QueryEngineInputBundle
from query_engine.models.knowledge_base import (
    CompanyKnowledgeBase,
    ConflictCandidateRecord,
    ConflictDataset,
    ConflictRecord,
    FinancialDataset,
    FinancialDatasetIndexes,
    FinancialRecord,
    IndexBucket,
    InsightDataset,
    InsightDatasetIndexes,
    InsightRecord,
    KnowledgeBaseMetadata,
    KnowledgeBaseValidationResult,
    WorkbookCellCitation,
    confidence_bucket,
    make_index,
    normalize_key,
    stable_id,
)
from shared.models.financial_year_consolidation import (
    ConsolidationCandidate,
    ConsolidationGroup,
)
from shared.models.metric_value import MetricValue
from workbook_population.models.workbook_cell_mapping import WorkbookCellMappingRecord


class QueryEnginePhase1Report(BaseModel):
    """Operational report for immutable knowledge-base construction."""

    model_config = ConfigDict(extra="forbid")

    financial_records_loaded: int = Field(..., ge=0)
    insight_records_loaded: int = Field(..., ge=0)
    conflict_records_loaded: int = Field(..., ge=0)
    index_counts: dict[str, dict[str, int]] = Field(default_factory=dict)
    validation_results: dict[str, Any] = Field(default_factory=dict)


class KnowledgeBaseBuilder:
    """Transform a QueryEngineInputBundle into a CompanyKnowledgeBase."""

    def __init__(
        self,
        *,
        report_path: str | Path = "output/query_engine_phase1_report.json",
    ) -> None:
        """Initialize builder configuration."""

        self._report_path = Path(report_path)
        self._last_report: QueryEnginePhase1Report | None = None

    @property
    def last_report(self) -> QueryEnginePhase1Report | None:
        """Return the last Phase 1 build report."""

        return self._last_report

    def build(self, bundle: QueryEngineInputBundle) -> CompanyKnowledgeBase:
        """Build, validate, and report on an immutable knowledge base."""

        metadata = self._metadata(bundle)
        conflict_dataset = self._conflict_dataset(bundle)
        financial_dataset = self._financial_dataset(bundle, conflict_dataset)
        insight_dataset = self._insight_dataset(bundle)
        validation_result = self._validate(
            bundle=bundle,
            financial_dataset=financial_dataset,
            insight_dataset=insight_dataset,
            conflict_dataset=conflict_dataset,
        )
        knowledge_base = CompanyKnowledgeBase(
            metadata=metadata,
            financial_dataset=financial_dataset,
            insight_dataset=insight_dataset,
            conflict_dataset=conflict_dataset,
            validation_result=validation_result,
        )
        report = QueryEnginePhase1Report(
            financial_records_loaded=len(financial_dataset.records),
            insight_records_loaded=len(insight_dataset.records),
            conflict_records_loaded=len(conflict_dataset.records),
            index_counts={
                "financial": financial_dataset.indexes.count_summary(),
                "insight": insight_dataset.indexes.count_summary(),
                "conflict": {
                    "records": len(conflict_dataset.records),
                    "unresolved": len(conflict_dataset.unresolved_conflicts),
                },
            },
            validation_results=validation_result.model_dump(mode="json"),
        )
        self._write_report(report)
        self._last_report = report
        return knowledge_base

    @staticmethod
    def _metadata(bundle: QueryEngineInputBundle) -> KnowledgeBaseMetadata:
        workbook_result = bundle.workbook_result
        return KnowledgeBaseMetadata(
            schema_version=bundle.schema_version,
            workbook_id=bundle.workbook_id,
            workbook_fingerprint=bundle.workbook_fingerprint,
            company_name=bundle.company_name,
            report_years=tuple(bundle.report_years),
            workbook_output_file_path=workbook_result.output_file_path,
            workbook_mode=workbook_result.workbook_mode,
            metrics_written=workbook_result.metrics_written,
            sheets_created=tuple(workbook_result.sheets_created),
            sheets_reused=tuple(workbook_result.sheets_reused),
            sheets_replaced=tuple(workbook_result.sheets_replaced),
        )

    def _financial_dataset(
        self,
        bundle: QueryEngineInputBundle,
        conflict_dataset: ConflictDataset,
    ) -> FinancialDataset:
        group_by_key = {
            (group.metric, group.value_year): group
            for group in bundle.financial_year_consolidation_result.groups
        }
        conflict_record_by_key = {
            (record.metric, record.value_year): record
            for record in conflict_dataset.records
        }
        mapping_by_key = _cell_mapping_by_key(bundle.workbook_cell_mappings)

        records: list[FinancialRecord] = []
        for metric_value in bundle.financial_year_consolidation_result.metric_values:
            group = group_by_key.get((metric_value.metric, metric_value.value_year))
            candidate = group.selected if group is not None else None
            conflict_record = conflict_record_by_key.get(
                (metric_value.metric, metric_value.value_year)
            )
            mapping = mapping_by_key.get(_metric_value_key(metric_value))
            records.append(
                self._financial_record(
                    bundle=bundle,
                    metric_value=metric_value,
                    candidate=candidate,
                    group=group,
                    conflict_record=conflict_record,
                    mapping=mapping,
                )
            )

        return FinancialDataset(
            records=tuple(records),
            indexes=FinancialDatasetIndexes(
                by_metric=make_index(
                    [(record.metric, record.record_id) for record in records]
                ),
                by_canonical_metric=make_index(
                    [(record.canonical_metric, record.record_id) for record in records]
                ),
                by_value_year=make_index(
                    [(str(record.value_year), record.record_id) for record in records]
                ),
                by_source_report_year=make_index(
                    [
                        (str(record.source_report_year), record.record_id)
                        for record in records
                    ]
                ),
                by_statement_scope=make_index(
                    [(record.statement_scope, record.record_id) for record in records]
                ),
            ),
        )

    @staticmethod
    def _financial_record(
        *,
        bundle: QueryEngineInputBundle,
        metric_value: MetricValue,
        candidate: ConsolidationCandidate | None,
        group: ConsolidationGroup | None,
        conflict_record: ConflictRecord | None,
        mapping: WorkbookCellMappingRecord | None,
    ) -> FinancialRecord:
        source_class = candidate.source_class if candidate else "unclassified"
        statement_scope = candidate.statement_scope if candidate else "unknown"
        normalization_confidence = (
            candidate.normalization_confidence if candidate else 0.0
        )
        source_confidence = candidate.source_confidence if candidate else 0.0
        original_metric = candidate.original_metric if candidate else metric_value.metric
        requires_review = candidate.requires_review if candidate else True

        record_id = stable_id(
            "fin",
            {
                "workbook_fingerprint": bundle.workbook_fingerprint,
                "metric": metric_value.metric,
                "value_year": metric_value.value_year,
                "source_report_year": metric_value.source_report_year,
                "table_type": metric_value.table_type,
                "page_number": metric_value.page_number,
            },
        )
        citation = WorkbookCellCitation(
            sheet_name=mapping.sheet_name if mapping else None,
            row=mapping.row if mapping else None,
            column=mapping.column if mapping else None,
            cell_reference=mapping.cell_reference if mapping else None,
            write_status=mapping.write_status if mapping else None,
            citation_status="cell_mapped" if mapping else "missing",
        )

        return FinancialRecord(
            record_id=record_id,
            metric=metric_value.metric,
            canonical_metric=metric_value.metric,
            value_year=metric_value.value_year,
            source_report_year=metric_value.source_report_year,
            value=metric_value.value,
            page_number=metric_value.page_number,
            table_type=metric_value.table_type,
            source_class=source_class,
            statement_scope=statement_scope,
            normalization_confidence=normalization_confidence,
            source_confidence=source_confidence,
            original_metric=original_metric,
            requires_review=requires_review,
            workbook_citation=citation,
            conflict_group_id=(
                conflict_record.conflict_group_id if conflict_record else None
            ),
            candidate_count=group.candidate_count if group else 1,
            is_duplicate_group=group.is_duplicate_group if group else False,
            is_conflict_group=group.is_conflict_group if group else False,
            conflict_resolved=group.conflict_resolved if group else True,
            unresolved_conflict=group.unresolved_conflict if group else False,
            conflict_status=group.conflict_status if group else "no_conflict",
            resolution_reason=group.resolution_reason if group else "single_candidate",
        )

    def _insight_dataset(self, bundle: QueryEngineInputBundle) -> InsightDataset:
        records: list[InsightRecord] = []
        for source_report_year, result in sorted(
            bundle.insights_results_by_report_year.items()
        ):
            for insight_index, insight in enumerate(result.insights):
                category = normalize_key(insight.area)
                text_hash = stable_id(
                    "text",
                    {
                        "area": insight.area,
                        "takeaway": insight.takeaway,
                        "section": insight.source_section,
                        "page": insight.page_number,
                    },
                )
                insight_id = stable_id(
                    "insight",
                    {
                        "workbook_fingerprint": bundle.workbook_fingerprint,
                        "source_report_year": source_report_year,
                        "value_year": insight.value_year,
                        "page_number": insight.page_number,
                        "index": insight_index,
                        "text_hash": text_hash,
                    },
                )
                records.append(
                    InsightRecord(
                        insight_id=insight_id,
                        value_year=insight.value_year,
                        source_report_year=insight.source_report_year,
                        category=category,
                        topic=category,
                        area=insight.area,
                        takeaway=insight.takeaway,
                        source_section=insight.source_section,
                        page_number=insight.page_number,
                        confidence=insight.confidence,
                        confidence_bucket=confidence_bucket(insight.confidence),
                        workbook_sheet_name="Insights",
                    )
                )

        return InsightDataset(
            records=tuple(records),
            indexes=InsightDatasetIndexes(
                by_report_year=make_index(
                    [(str(record.source_report_year), record.insight_id) for record in records]
                ),
                by_category=make_index(
                    [(record.category, record.insight_id) for record in records]
                ),
                by_topic=make_index(
                    [(record.topic, record.insight_id) for record in records]
                ),
                by_confidence=make_index(
                    [(record.confidence_bucket, record.insight_id) for record in records]
                ),
            ),
        )

    @staticmethod
    def _conflict_dataset(bundle: QueryEngineInputBundle) -> ConflictDataset:
        records: list[ConflictRecord] = []
        for group in bundle.financial_year_consolidation_result.groups:
            selected = _candidate_record(
                bundle.workbook_fingerprint,
                group.selected,
            )
            competing = tuple(
                _candidate_record(bundle.workbook_fingerprint, candidate)
                for candidate in group.competing_candidates
            )
            candidates = (selected, *competing)
            conflict_group_id = stable_id(
                "conflict",
                {
                    "workbook_fingerprint": bundle.workbook_fingerprint,
                    "metric": group.metric,
                    "value_year": group.value_year,
                },
            )
            records.append(
                ConflictRecord(
                    conflict_group_id=conflict_group_id,
                    metric=group.metric,
                    canonical_metric=group.metric,
                    value_year=group.value_year,
                    selected_candidate_id=selected.candidate_id,
                    candidate_count=group.candidate_count,
                    candidates=candidates,
                    competing_candidates=competing,
                    is_duplicate_group=group.is_duplicate_group,
                    is_conflict_group=group.is_conflict_group,
                    conflict_resolved=group.conflict_resolved,
                    unresolved_conflict=group.unresolved_conflict,
                    conflict_status=group.conflict_status,
                    resolution_reason=group.resolution_reason,
                )
            )

        unresolved = tuple(record for record in records if record.unresolved_conflict)
        return ConflictDataset(records=tuple(records), unresolved_conflicts=unresolved)

    @staticmethod
    def _validate(
        *,
        bundle: QueryEngineInputBundle,
        financial_dataset: FinancialDataset,
        insight_dataset: InsightDataset,
        conflict_dataset: ConflictDataset,
    ) -> KnowledgeBaseValidationResult:
        errors: list[str] = []
        warnings: list[str] = []
        report_years = set(bundle.report_years)

        financial_ids = [record.record_id for record in financial_dataset.records]
        if len(financial_ids) != len(set(financial_ids)):
            errors.append("financial_dataset contains duplicate record_id values")

        insight_ids = [record.insight_id for record in insight_dataset.records]
        if len(insight_ids) != len(set(insight_ids)):
            errors.append("insight_dataset contains duplicate insight_id values")

        conflict_ids = [record.conflict_group_id for record in conflict_dataset.records]
        if len(conflict_ids) != len(set(conflict_ids)):
            errors.append("conflict_dataset contains duplicate conflict_group_id values")

        conflict_id_set = set(conflict_ids)
        for record in financial_dataset.records:
            if record.source_report_year not in report_years:
                errors.append(
                    f"financial record {record.record_id} has source_report_year "
                    f"{record.source_report_year} outside report_years"
                )
            if record.value_year > record.source_report_year:
                errors.append(
                    f"financial record {record.record_id} has value_year after "
                    "source_report_year"
                )
            if record.conflict_group_id and record.conflict_group_id not in conflict_id_set:
                errors.append(
                    f"financial record {record.record_id} references missing "
                    f"conflict group {record.conflict_group_id}"
                )
            if record.workbook_citation.citation_status == "missing":
                warnings.append(
                    f"financial record {record.record_id} has no workbook cell mapping"
                )

        for record in insight_dataset.records:
            if record.source_report_year not in report_years:
                errors.append(
                    f"insight record {record.insight_id} has source_report_year "
                    f"{record.source_report_year} outside report_years"
                )
            if record.value_year > record.source_report_year:
                errors.append(
                    f"insight record {record.insight_id} has value_year after "
                    "source_report_year"
                )

        valid_financial_ids = set(financial_ids)
        for index_name, buckets in _financial_index_buckets(financial_dataset).items():
            for bucket in buckets:
                missing = set(bucket.record_ids) - valid_financial_ids
                if missing:
                    errors.append(
                        f"financial index {index_name}/{bucket.key} references "
                        f"unknown records: {sorted(missing)}"
                    )

        valid_insight_ids = set(insight_ids)
        for index_name, buckets in _insight_index_buckets(insight_dataset).items():
            for bucket in buckets:
                missing = set(bucket.record_ids) - valid_insight_ids
                if missing:
                    errors.append(
                        f"insight index {index_name}/{bucket.key} references "
                        f"unknown records: {sorted(missing)}"
                    )

        return KnowledgeBaseValidationResult(
            is_valid=not errors,
            errors=tuple(_deduplicate(errors)),
            warnings=tuple(_deduplicate(warnings)),
        )

    def _write_report(self, report: QueryEnginePhase1Report) -> None:
        self._report_path.parent.mkdir(parents=True, exist_ok=True)
        self._report_path.write_text(
            json.dumps(report.model_dump(mode="json"), indent=2, sort_keys=True),
            encoding="utf-8",
        )


def _cell_mapping_by_key(
    mappings: list[WorkbookCellMappingRecord],
) -> dict[tuple[str, int, int, str], WorkbookCellMappingRecord]:
    by_key: dict[tuple[str, int, int, str], WorkbookCellMappingRecord] = {}
    for mapping in mappings:
        if mapping.write_status != "written":
            continue
        by_key.setdefault(
            (
                mapping.metric,
                mapping.value_year,
                mapping.source_report_year,
                mapping.table_type,
            ),
            mapping,
        )
    return by_key


def _metric_value_key(metric_value: MetricValue) -> tuple[str, int, int, str]:
    return (
        metric_value.metric,
        metric_value.value_year,
        metric_value.source_report_year,
        metric_value.table_type,
    )


def _candidate_record(
    workbook_fingerprint: str,
    candidate: ConsolidationCandidate,
) -> ConflictCandidateRecord:
    candidate_id = stable_id(
        "cand",
        {
            "workbook_fingerprint": workbook_fingerprint,
            "metric": candidate.metric,
            "value_year": candidate.value_year,
            "source_report_year": candidate.source_report_year,
            "page_number": candidate.page_number,
            "table_type": candidate.table_type,
            "value": candidate.value,
            "original_metric": candidate.original_metric,
        },
    )
    return ConflictCandidateRecord(
        candidate_id=candidate_id,
        metric=candidate.metric,
        canonical_metric=candidate.metric,
        value_year=candidate.value_year,
        source_report_year=candidate.source_report_year,
        value=candidate.value,
        page_number=candidate.page_number,
        table_type=candidate.table_type,
        source_class=candidate.source_class,
        statement_scope=candidate.statement_scope,
        normalization_confidence=candidate.normalization_confidence,
        source_confidence=candidate.source_confidence,
        original_metric=candidate.original_metric,
        requires_review=candidate.requires_review,
    )


def _financial_index_buckets(
    dataset: FinancialDataset,
) -> dict[str, tuple[IndexBucket, ...]]:
    return {
        "by_metric": dataset.indexes.by_metric,
        "by_canonical_metric": dataset.indexes.by_canonical_metric,
        "by_value_year": dataset.indexes.by_value_year,
        "by_source_report_year": dataset.indexes.by_source_report_year,
        "by_statement_scope": dataset.indexes.by_statement_scope,
    }


def _insight_index_buckets(
    dataset: InsightDataset,
) -> dict[str, tuple[IndexBucket, ...]]:
    return {
        "by_report_year": dataset.indexes.by_report_year,
        "by_category": dataset.indexes.by_category,
        "by_topic": dataset.indexes.by_topic,
        "by_confidence": dataset.indexes.by_confidence,
    }


def _deduplicate(values: list[str]) -> list[str]:
    seen: set[str] = set()
    deduplicated: list[str] = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        deduplicated.append(value)
    return deduplicated


__all__ = ["KnowledgeBaseBuilder", "QueryEnginePhase1Report"]
