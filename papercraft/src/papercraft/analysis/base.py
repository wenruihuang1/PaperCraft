"""Stable paper-analysis boundary consuming frozen DocumentIR 1.0."""

from __future__ import annotations

from abc import ABC, abstractmethod

from papercraft.models.document_ir import DocumentIR
from papercraft.models.paper_analysis import PaperAnalysis


class PaperAnalyzer(ABC):
    """Analyze paper logic without depending on a PDF adapter implementation."""

    @abstractmethod
    def analyze(self, document_ir: DocumentIR) -> PaperAnalysis:
        """Return a source-grounded analysis for one DocumentIR 1.0 artifact."""


class PaperAnalysisError(ValueError):
    """Raised when a conservative analyzer cannot satisfy the minimum contract."""

