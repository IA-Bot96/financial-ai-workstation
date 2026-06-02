"""Tests for QAE Phase 7 deterministic orchestration."""

import json
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[2]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from qualitative_analysis_engine.models import (  # noqa: E402
    CategoryStatus,
    QualitativeRunResult,
    RunStatus,
)
from qualitative_analysis_engine.services import (  # noqa: E402
    QualitativeAnalysisOrchestrator,
    QualitativeAnalysisRunArtifacts,
)


def _insight(**overrides) -> dict:
    payload = {
        "value_year": 2025,
        "source_report_year": 2025,
        "area": "capacity expansion",
        "takeaway": "Capacity increased after commissioning of a new line.",
        "source_section": "Business Review",
        "page_number": 10,
        "confidence": 0.9,
    }
    payload.update(overrides)
    return payload


def _orchestrator() -> QualitativeAnalysisOrchestrator:
    return QualitativeAnalysisOrchestrator()


def test_orchestrator_returns_authoritative_run_result() -> None:
    run_result = _orchestrator().run(
        [
            _insight(page_number=10),
            _insight(
                page_number=11,
                takeaway="Capacity expansion improved production flexibility.",
            ),
        ],
        entity_ref="lucky_cement",
        workbook_fingerprint="fp_lucky_2025",
    )

    assert isinstance(run_result, QualitativeRunResult)
    assert run_result.entity_ref == "lucky_cement"
    assert run_result.versions.taxonomy_version == "1.0.0"
    assert run_result.versions.authority_matrix_version == "1.0.0"
    assert run_result.fve_handoff.narrative_only is True
    assert run_result.coverage_summary.raw == 2


def test_orchestrator_run_artifacts_preserve_intermediate_counts() -> None:
    artifacts = _orchestrator().run_with_artifacts(
        [
            _insight(area="capacity expansion", page_number=10),
            _insight(
                area="demand outlook",
                takeaway="Demand increased due to market recovery.",
                source_section="Outlook",
                page_number=20,
            ),
            _insight(
                area="demand outlook",
                takeaway="Demand declined due to weak market conditions.",
                source_section="Outlook",
                page_number=21,
            ),
        ],
        entity_ref="lucky_cement",
        workbook_fingerprint="fp_lucky_2025",
    )

    assert isinstance(artifacts, QualitativeAnalysisRunArtifacts)
    assert len(artifacts.signals) == 3
    assert artifacts.coverage_result.total_signal_count == 3
    assert len(artifacts.assembly_result.themes) == 2
    assert len(artifacts.category_results) == 6
    assert artifacts.run_result.divergence_summary.total_divergences == 1
    assert artifacts.run_metadata["signals_processed"] == 3
    assert artifacts.run_metadata["themes_created"] == 2
    assert artifacts.run_metadata["divergence_count"] == 1


def test_orchestrator_preserves_unmapped_reporting_and_skip_accounting() -> None:
    artifacts = _orchestrator().run_with_artifacts(
        [
            _insight(
                area="Unknown topic",
                takeaway="This narrative does not map to the frozen taxonomy.",
            )
        ],
        entity_ref="lucky_cement",
        workbook_fingerprint="fp_lucky_2025",
    )

    statuses = {
        result.category_ref: result.status for result in artifacts.category_results
    }

    assert artifacts.run_result.run_status == RunStatus.INSUFFICIENT_COVERAGE
    assert artifacts.run_result.unmapped_summary.total_unmapped == 1
    assert statuses["strategy"] == CategoryStatus.SKIPPED_NO_ELIGIBLE_SIGNALS
    assert "strategy" in artifacts.run_metadata["categories_skipped"]


def test_orchestrator_smoke_audit_payload_contains_required_sections() -> None:
    artifacts = _orchestrator().run_with_artifacts(
        [
            _insight(page_number=10),
            _insight(
                page_number=11,
                area="cost optimization",
                takeaway="Energy efficiency initiatives reduced operating costs.",
            ),
        ],
        entity_ref="lucky_cement",
        workbook_fingerprint="fp_lucky_2025",
    )

    payload = _orchestrator().to_smoke_audit_payload(artifacts)

    assert payload["insight_count"] == 2
    assert payload["signal_count"] == 2
    assert payload["theme_count"] == 2
    assert payload["run_status"] == RunStatus.INSUFFICIENT_COVERAGE.value
    assert "coverage_summary" in payload
    assert "divergence_summary" in payload
    assert "unmapped_summary" in payload
    assert payload["constraints_observed"]["llm_logic"] is False


def test_orchestrator_writes_smoke_audit() -> None:
    output_path = Path("output/.tmp_qae_tests/qae_smoke.json")

    artifacts = _orchestrator().write_smoke_audit(
        output_path,
        [_insight(page_number=10)],
        entity_ref="lucky_cement",
        workbook_fingerprint="fp_lucky_2025",
    )

    payload = json.loads(output_path.read_text(encoding="utf-8"))
    assert payload["signal_count"] == 1
    assert payload["run_metadata"]["signals_processed"] == 1
    assert (
        payload["taxonomy_version"]
        == artifacts.run_result.versions.taxonomy_version
    )
