"""Deterministic QAE classification services."""

from .category_aggregation import CategoryAggregationService
from .coverage_gate import (
    CategoryAdmissionStatus,
    CategoryCoverageDecision,
    QualitativeCoverageGate,
    QualitativeCoverageGateResult,
)
from .insight_to_signal_adapter import InsightToSignalAdapter
from .mapping_audit import TaxonomyMappingAuditService
from .mapping_confidence import MappingConfidenceComposer
from .orchestrator import (
    QualitativeAnalysisOrchestrator,
    QualitativeAnalysisRunArtifacts,
)
from .scorecard import QualitativeScorecardService
from .section_router import SectionRoute, SourceSectionRouter
from .taxonomy_loader import (
    CategoryDefinition,
    TaxonomyDefinition,
    TaxonomyLoader,
    ThemeDefinition,
)
from .theme_assembly import (
    ThemeAssemblyResult,
    ThemeAssemblyService,
    UnmappedSignalReference,
)
from .theme_canonicalizer import ThemeCanonicalizationResult, ThemeCanonicalizer

__all__ = [
    "CategoryDefinition",
    "CategoryAdmissionStatus",
    "CategoryAggregationService",
    "CategoryCoverageDecision",
    "InsightToSignalAdapter",
    "MappingConfidenceComposer",
    "QualitativeAnalysisOrchestrator",
    "QualitativeAnalysisRunArtifacts",
    "QualitativeCoverageGate",
    "QualitativeCoverageGateResult",
    "QualitativeScorecardService",
    "SectionRoute",
    "SourceSectionRouter",
    "TaxonomyDefinition",
    "TaxonomyLoader",
    "TaxonomyMappingAuditService",
    "ThemeAssemblyResult",
    "ThemeAssemblyService",
    "ThemeCanonicalizationResult",
    "ThemeCanonicalizer",
    "ThemeDefinition",
    "UnmappedSignalReference",
]
