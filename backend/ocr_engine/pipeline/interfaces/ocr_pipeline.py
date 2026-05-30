"""Interface for the OCR pipeline orchestrator."""

from abc import ABC, abstractmethod

from shared.models.company_context import CompanyContext


class IOCRPipeline(ABC):
    """Contract for the OCR workflow entry point."""

    @abstractmethod
    def process(self, context: CompanyContext) -> CompanyContext:
        """Run all OCR workflow layers and return the populated context."""
