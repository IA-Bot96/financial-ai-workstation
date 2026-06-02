"""Mapping-confidence composition for QAE taxonomy classification."""

from __future__ import annotations

from qualitative_analysis_engine.models import MappingMethod


class MappingConfidenceComposer:
    """Compose deterministic mapping confidence from contract confidence inputs."""

    EXACT_CONFIDENCE = 1.0
    ALIAS_CONFIDENCE = 0.9
    KEYWORD_CONFIDENCE = 0.65
    SECTION_ONLY_CONFIDENCE = 0.35
    UNMAPPED_CONFIDENCE = 0.0
    SECTION_THEME_CONFLICT_PENALTY = 0.15

    def method_confidence(self, mapping_method: MappingMethod) -> float:
        """Return the base confidence for a mapping method."""

        if mapping_method == MappingMethod.EXACT:
            return self.EXACT_CONFIDENCE
        if mapping_method == MappingMethod.ALIAS:
            return self.ALIAS_CONFIDENCE
        if mapping_method == MappingMethod.KEYWORD:
            return self.KEYWORD_CONFIDENCE
        if mapping_method == MappingMethod.SECTION_ONLY:
            return self.SECTION_ONLY_CONFIDENCE
        return self.UNMAPPED_CONFIDENCE

    def compose(
        self,
        *,
        mapping_confidence: float,
        extraction_confidence: float = 1.0,
        section_confidence: float | None = None,
        section_theme_conflict: bool = False,
    ) -> float:
        """Compose confidence using the frozen min-floor rule."""

        confidence_inputs = [mapping_confidence, extraction_confidence]
        if section_confidence is not None:
            confidence_inputs.append(section_confidence)
        confidence = min(confidence_inputs)
        if section_theme_conflict:
            confidence = max(0.0, confidence - self.SECTION_THEME_CONFLICT_PENALTY)
        return round(confidence, 6)


__all__ = ["MappingConfidenceComposer"]

