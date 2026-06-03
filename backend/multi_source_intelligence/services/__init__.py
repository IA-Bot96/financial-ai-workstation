"""MSIL services."""

from .annual_report_adapter import (
    AnnualReportAdapter,
    AnnualReportAdapterMappingFailure,
    AnnualReportAdapterResult,
)
from .authority_assignment import (
    AuthorityAssignmentRequest,
    AuthorityAssignmentResult,
    AuthorityAssignmentService,
)
from .contract_integrity_validator import ContractIntegrityValidator
from .default_entity_registry import default_entity_registry
from .entity_resolver import EntityResolver
from .evidence_comparison import (
    CorroborationService,
    DivergenceService,
    build_corroboration_audit,
    build_divergence_audit,
)
from .official_source_adapters import (
    CompanyPayoutAdapter,
    CompanyPayoutRecord,
    OfficialSourceAdapterResult,
    OfficialSourceIngestionFailure,
    PSXAnnouncementAdapter,
    PSXAnnouncementRecord,
    SECPNoticeAdapter,
    SECPNoticeRecord,
    build_official_sources_audit,
)
from .timeline import (
    SupersessionService,
    TimelineAssemblyService,
    build_timeline_audit,
)

__all__ = [
    "AnnualReportAdapter",
    "AnnualReportAdapterMappingFailure",
    "AnnualReportAdapterResult",
    "AuthorityAssignmentRequest",
    "AuthorityAssignmentResult",
    "AuthorityAssignmentService",
    "ContractIntegrityValidator",
    "CorroborationService",
    "DivergenceService",
    "EntityResolver",
    "CompanyPayoutAdapter",
    "CompanyPayoutRecord",
    "OfficialSourceAdapterResult",
    "OfficialSourceIngestionFailure",
    "PSXAnnouncementAdapter",
    "PSXAnnouncementRecord",
    "SECPNoticeAdapter",
    "SECPNoticeRecord",
    "SupersessionService",
    "TimelineAssemblyService",
    "build_corroboration_audit",
    "build_divergence_audit",
    "build_official_sources_audit",
    "build_timeline_audit",
    "default_entity_registry",
]
