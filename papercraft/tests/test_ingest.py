from __future__ import annotations

from pathlib import Path

import fitz
import pytest

from papercraft.ingest import PDFAdapter, PyMuPDFAdapter, UnsupportedPDFError
from papercraft.ingest.pymupdf_adapter import _asset_crop


def _write_text_pdf(path: Path, text: str, pages: int = 2) -> None:
    document = fitz.open()
    for page_number in range(pages):
        page = document.new_page(width=612, height=792)
        page.insert_textbox(
            fitz.Rect(50, 50, 562, 742),
            f"Page {page_number + 1}\n{text}",
            fontsize=10,
        )
    document.set_metadata({"title": "Synthetic English Paper", "author": "Test Author"})
    document.save(path)


def test_adapter_boundary_is_abstract():
    assert PDFAdapter.__abstractmethods__ == {"detect", "extract"}


def test_supported_english_text_pdf_extracts_traceable_blocks(tmp_path):
    sentence = (
        "This is an English research document and we use the method for the evaluation. "
        "The result is reported in the paper and the model is compared with a baseline. "
    )
    pdf = tmp_path / "supported.pdf"
    _write_text_pdf(pdf, sentence * 12)

    adapter = PyMuPDFAdapter()
    report = adapter.detect(pdf)
    assert report.status == "supported"
    assert report.rejection_codes == []

    ir = adapter.extract(pdf, "ppr_synthetic", tmp_path / "output")
    assert len(ir.pages) == 2
    assert ir.blocks
    assert len(ir.source_refs) >= len(ir.blocks)
    block_by_id = {block.block_id: block for block in ir.blocks}
    for ref in [item for item in ir.source_refs if item.source_type == "text_span"]:
        block = block_by_id[ref.locator.block_id]
        assert block.text[ref.locator.char_start : ref.locator.char_end] == ref.quote


def test_blank_pdf_is_rejected_as_no_text_layer(tmp_path):
    pdf = tmp_path / "blank.pdf"
    document = fitz.open()
    document.new_page()
    document.save(pdf)
    report = PyMuPDFAdapter().detect(pdf)
    assert report.status == "rejected"
    assert "NO_TEXT_LAYER" in report.rejection_codes


def test_raster_only_pdf_is_rejected_as_scanned(tmp_path):
    pdf = tmp_path / "scan.pdf"
    document = fitz.open()
    page = document.new_page(width=612, height=792)
    pixmap = fitz.Pixmap(fitz.csRGB, fitz.IRect(0, 0, 32, 32), False)
    pixmap.clear_with(220)
    page.insert_image(page.rect, pixmap=pixmap)
    document.save(pdf)
    report = PyMuPDFAdapter().detect(pdf)
    assert report.status == "rejected"
    assert "SCANNED_PDF" in report.rejection_codes
    assert "NO_TEXT_LAYER" in report.rejection_codes


def test_ocr_backed_scan_is_still_rejected_as_scanned(tmp_path):
    pdf = tmp_path / "ocr-scan.pdf"
    document = fitz.open()
    sentence = (
        "This is an English research paper with a recognized OCR text layer. "
        "The method and the experiment are described for evaluation. "
    )
    for _ in range(2):
        page = document.new_page(width=612, height=792)
        pixmap = fitz.Pixmap(fitz.csRGB, fitz.IRect(0, 0, 32, 32), False)
        pixmap.clear_with(220)
        page.insert_image(page.rect, pixmap=pixmap)
        page.insert_textbox(fitz.Rect(50, 50, 562, 742), sentence * 12, fontsize=10)
    document.save(pdf)

    report = PyMuPDFAdapter().detect(pdf)
    assert report.status == "rejected"
    assert "SCANNED_PDF" in report.rejection_codes
    assert "NO_TEXT_LAYER" not in report.rejection_codes


def test_non_english_latin_pdf_is_rejected(tmp_path):
    spanish = (
        "Este documento describe resultados experimentales para modelos científicos. "
        "Los métodos propuestos reducen errores durante evaluaciones controladas. "
    )
    pdf = tmp_path / "spanish.pdf"
    _write_text_pdf(pdf, spanish * 12)
    report = PyMuPDFAdapter().detect(pdf)
    assert report.status == "rejected"
    assert "NON_ENGLISH_PDF" in report.rejection_codes


def test_malformed_pdf_is_rejected_and_extract_raises(tmp_path):
    pdf = tmp_path / "broken.pdf"
    pdf.write_bytes(b"not a pdf")
    adapter = PyMuPDFAdapter()
    report = adapter.detect(pdf)
    assert report.status == "rejected"
    assert report.rejection_codes == ["MALFORMED_PDF"]
    with pytest.raises(UnsupportedPDFError):
        adapter.extract(pdf, "ppr_broken", tmp_path / "output")


def test_figure_crop_stops_before_caption():
    document = fitz.open()
    page = document.new_page(width=612, height=792)
    pixmap = fitz.Pixmap(fitz.csRGB, fitz.IRect(0, 0, 200, 100), False)
    pixmap.clear_with(220)
    page.insert_image(fitz.Rect(60, 80, 300, 190), pixmap=pixmap)
    caption_bbox = fitz.Rect(60, 200, 300, 235)

    crop = _asset_crop(page, caption_bbox, "figure", "Fig. 1. Method overview.")

    assert crop.y1 < caption_bbox.y0
