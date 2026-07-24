"""Adapter boundary and capability result for deterministic PDF ingestion."""

from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Literal

from pydantic import Field

from papercraft.models.common import PaperId, Sha256, StrictModel
from papercraft.models.document_ir import DocumentIR


class PageCapability(StrictModel):
    page_number: int = Field(ge=1)
    text_characters: int = Field(ge=0)
    image_coverage_ratio: float = Field(ge=0.0, le=1.0)


class CapabilityMetrics(StrictModel):
    page_count: int = Field(ge=1)
    total_text_characters: int = Field(ge=0)
    text_page_ratio: float = Field(ge=0.0, le=1.0)
    raster_dominant_page_ratio: float = Field(ge=0.0, le=1.0)
    latin_letter_ratio: float = Field(ge=0.0, le=1.0)
    english_function_word_ratio: float = Field(ge=0.0, le=1.0)


class PDFCapabilityReport(StrictModel):
    file_name: str
    sha256: Sha256
    status: Literal["supported", "rejected"]
    rejection_codes: list[
        Literal[
            "ENCRYPTED_PDF",
            "NO_TEXT_LAYER",
            "SCANNED_PDF",
            "NON_ENGLISH_PDF",
            "MALFORMED_PDF",
        ]
    ]
    metrics: CapabilityMetrics
    pages: list[PageCapability]


class UnsupportedPDFError(ValueError):
    def __init__(self, report: PDFCapabilityReport):
        self.report = report
        codes = ", ".join(report.rejection_codes) or "unknown reason"
        super().__init__(f"unsupported PDF: {codes}")


class PDFAdapter(ABC):
    """Stable boundary so ingestion is not coupled to one PDF library."""

    @abstractmethod
    def detect(self, pdf_path: Path) -> PDFCapabilityReport:
        """Return a deterministic support/rejection report without extracting IR."""

    @abstractmethod
    def extract(self, pdf_path: Path, paper_id: PaperId, output_dir: Path) -> DocumentIR:
        """Build DocumentIR or raise UnsupportedPDFError."""

