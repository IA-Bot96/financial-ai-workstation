"""JSON serializer and loader for Query Engine input bundles."""

from __future__ import annotations

import json
from pathlib import Path

from query_engine.models.input_bundle import QueryEngineInputBundle
from query_engine.services.fingerprint_service import QueryEngineFingerprintService


class QueryEngineBundleSerializer:
    """Persist Query Engine input bundles as deterministic JSON sidecars."""

    def serialize(
        self,
        bundle: QueryEngineInputBundle,
        output_path: str | Path | None = None,
    ) -> Path:
        """Write bundle JSON and return the sidecar path."""

        sidecar_path = (
            Path(output_path)
            if output_path is not None
            else _default_sidecar_path(bundle.workbook_result.output_file_path)
        )
        sidecar_path.parent.mkdir(parents=True, exist_ok=True)
        payload = bundle.model_dump(mode="json")
        sidecar_path.write_text(
            json.dumps(payload, indent=2, sort_keys=True),
            encoding="utf-8",
        )
        return sidecar_path


class QueryEngineBundleLoader:
    """Load and validate Query Engine input bundles from JSON sidecars."""

    def __init__(
        self,
        *,
        fingerprint_service: QueryEngineFingerprintService | None = None,
    ) -> None:
        """Initialize loader dependencies."""

        self._fingerprint_service = fingerprint_service or QueryEngineFingerprintService()

    def load(self, sidecar_path: str | Path) -> QueryEngineInputBundle:
        """Read a JSON sidecar and return a validated input bundle."""

        payload = json.loads(Path(sidecar_path).read_text(encoding="utf-8"))
        bundle = QueryEngineInputBundle.model_validate(payload)
        validation = bundle.validate_contract()
        if not validation.is_valid:
            raise ValueError(
                "Invalid Query Engine input bundle: "
                + "; ".join(validation.errors)
            )
        workbook_path = Path(bundle.workbook_result.output_file_path)
        if workbook_path.exists():
            expected_fingerprint = self._fingerprint_service.workbook_fingerprint(
                workbook_path=workbook_path,
                structured_payload=bundle.stable_payload(),
            )
            if expected_fingerprint != bundle.workbook_fingerprint:
                raise ValueError(
                    "Invalid Query Engine input bundle: workbook_fingerprint "
                    "does not match workbook bytes and structured payload"
                )
        return bundle


def _default_sidecar_path(workbook_path: str) -> Path:
    path = Path(workbook_path)
    return path.with_suffix(".kb.json")


__all__ = ["QueryEngineBundleLoader", "QueryEngineBundleSerializer"]
