"""Deterministic workbook and sidecar fingerprint generation."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Mapping


class QueryEngineFingerprintService:
    """Generate stable fingerprints for Query Engine handoff bundles."""

    def workbook_bytes_hash(self, workbook_path: str | Path) -> str:
        """Return the SHA-256 hash of workbook bytes."""

        digest = hashlib.sha256()
        with Path(workbook_path).open("rb") as workbook_file:
            for chunk in iter(lambda: workbook_file.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()

    def structured_payload_hash(self, payload: Mapping[str, Any]) -> str:
        """Return a stable SHA-256 hash for a structured sidecar payload."""

        canonical = json.dumps(
            payload,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
        )
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    def workbook_fingerprint(
        self,
        *,
        workbook_path: str | Path,
        structured_payload: Mapping[str, Any],
    ) -> str:
        """Combine workbook bytes and sidecar payload hashes into one fingerprint."""

        workbook_hash = self.workbook_bytes_hash(workbook_path)
        payload_hash = self.structured_payload_hash(structured_payload)
        return hashlib.sha256(
            f"{workbook_hash}:{payload_hash}".encode("utf-8")
        ).hexdigest()


__all__ = ["QueryEngineFingerprintService"]
