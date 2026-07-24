"""Deterministic input adapters. Stage B provides PDF support only."""

from papercraft.ingest.base import PDFAdapter, PDFCapabilityReport, UnsupportedPDFError
from papercraft.ingest.pymupdf_adapter import PyMuPDFAdapter
from papercraft.ingest.arxiv import download_arxiv

__all__ = [
    "PDFAdapter",
    "PDFCapabilityReport",
    "UnsupportedPDFError",
    "PyMuPDFAdapter",
    "download_arxiv",
]
