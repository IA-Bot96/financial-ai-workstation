"""Tests for Query Engine v2 Phase P7 real-bundle validation."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

BACKEND_DIR = Path(__file__).resolve().parents[2]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from query_engine.services import (  # noqa: E402
    LUCKY_FINGERPRINT_PREFIX,
    QueryV2RealBundleValidator,
)


def _real_lucky_bundle() -> Path:
    candidates = sorted(
        Path("output").glob("lucky*.kb.json"),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )
    for candidate in candidates:
        if LUCKY_FINGERPRINT_PREFIX in candidate.read_text(
            encoding="utf-8",
            errors="ignore",
        ):
            return candidate
    pytest.skip("Real Lucky production bundle with expected fingerprint is unavailable.")


def test_real_bundle_validator_generates_required_p7_artifacts(tmp_path: Path) -> None:
    bundle_path = _real_lucky_bundle()
    audit_path = tmp_path / "query_v2_real_bundle_audit.json"
    report_path = tmp_path / "query_v2_real_bundle_validation_report.json"

    report = QueryV2RealBundleValidator(
        bundle_path=bundle_path,
        output_dir="output",
    ).write_validation_report(audit_path=audit_path, report_path=report_path)

    audit = json.loads(audit_path.read_text(encoding="utf-8"))
    persisted_report = json.loads(report_path.read_text(encoding="utf-8"))

    assert report.validation_passed is True
    assert persisted_report["validation_passed"] is True
    assert audit["queries_executed"] >= 8
    assert audit["fingerprint_prefix_matched"] is True
    assert audit["fixture_expectations"]["failed_expectations"] == 0
    assert audit["platform_invariants"]["every_shipped_claim_cited"] is True
    assert audit["platform_invariants"]["every_metric_carries_integrity_status"] is True
    assert audit["platform_invariants"]["no_authority_recomputation"] is True
    assert audit["platform_invariants"]["no_divergence_resolution"] is True
    assert audit["platform_invariants"]["no_confidence_inflation"] is True
    assert audit["citation_coverage_percent"] == 100.0
    assert audit["authority_coverage_percent"] == 100.0


def test_real_bundle_validation_corpus_covers_frozen_intent_families() -> None:
    bundle_path = _real_lucky_bundle()

    audit, _report = QueryV2RealBundleValidator(
        bundle_path=bundle_path,
        output_dir="output",
    ).run()

    covered = set(audit.intent_counts)
    assert {
        "factual_lookup",
        "metric_lookup",
        "qualitative_analysis",
        "forecast_validation",
        "comparison",
        "timeline",
        "risk_analysis",
        "source_exploration",
        "ambiguous",
        "unsupported",
    }.issubset(covered)
    assert audit.clarification_responses == 1
    assert audit.unsupported_responses == 1
