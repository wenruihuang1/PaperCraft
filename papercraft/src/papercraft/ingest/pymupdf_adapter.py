"""PyMuPDF implementation of deterministic English text-PDF ingestion."""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from pathlib import Path
from statistics import median
from typing import Any, Iterable

import fitz

from papercraft.ingest.base import (
    CapabilityMetrics,
    PageCapability,
    PDFAdapter,
    PDFCapabilityReport,
    UnsupportedPDFError,
)
from papercraft.models.common import PaperId
from papercraft.models.document_ir import (
    BoundingBox,
    DocumentIR,
    DocumentSource,
    PageInfo,
    PaperMetadata,
    SourceAsset,
    SourceBlock,
    SourceEquation,
    SourceLocator,
    SourceReference,
    SourceSection,
)


FIGURE_CAPTION_RE = re.compile(
    r"^\s*(figure|fig\.)\s*([0-9]+|[ivxlcdm]+)\s*[:.]",
    re.IGNORECASE,
)
TABLE_CAPTION_RE = re.compile(
    r"^\s*table\s*([0-9]+|[ivxlcdm]+)\s*[:.]",
    re.IGNORECASE,
)
IEEE_TABLE_CAPTION_RE = re.compile(
    r"^\s*TABLE\s+([0-9]+|[IVXLCDM]+)\s+(.+)",
    re.DOTALL,
)
EQUATION_LABEL_RE = re.compile(r"\(([0-9]{1,3})\)\s*$")
HEADING_RE = re.compile(
    r"^\s*(?:(?:[0-9]+|[ivxlcdm]+)[.)]?\s+)?"
    r"(abstract|introduction|background|related works?|(?:the\s+)?proposed method|"
    r"materials and methods|method(?:ology)?|approach|theory|"
    r"experiments?|results?|discussion|conclusion|limitations?|references|appendix)\b",
    re.IGNORECASE,
)
MATH_FONT_MARKERS = (
    "math",
    "symbol",
    "cmsy",
    "cmmi",
    "cmex",
    "stix",
    "mt extra",
    "mtsyn",
    "rblmi",
    "blex",
)
MATH_OPERATORS = set("=+-/*^∑∫≤≥≈→←±×÷∂∇∞∥")
ENGLISH_FUNCTION_WORDS = {
    "a",
    "an",
    "and",
    "are",
    "as",
    "be",
    "by",
    "for",
    "from",
    "in",
    "is",
    "of",
    "on",
    "our",
    "that",
    "the",
    "this",
    "to",
    "using",
    "we",
    "which",
    "with",
}
PROSE_EQUATION_LEADERS = (
    "where ",
    "here ",
    "compared ",
    "therefore ",
    "we ",
    "the ",
    "this ",
    "that ",
    "using ",
)


@dataclass
class _BlockCandidate:
    page: int
    text: str
    bbox: fitz.Rect
    max_font_size: float
    bold: bool
    lines: list[dict[str, Any]]
    block_type: str = "paragraph"
    section_id: str | None = None


class PyMuPDFAdapter(PDFAdapter):
    """No OCR, language model, remote service, or semantic inference."""

    minimum_total_characters = 500
    minimum_text_page_ratio = 0.5
    minimum_latin_ratio = 0.85
    minimum_english_word_ratio = 0.08

    def detect(self, pdf_path: Path) -> PDFCapabilityReport:
        digest = _sha256(pdf_path) if pdf_path.is_file() else f"sha256:{'0' * 64}"
        rejection_codes: list[str] = []
        pages: list[PageCapability] = []
        all_text: list[str] = []
        try:
            document = fitz.open(pdf_path)
        except Exception:
            return PDFCapabilityReport(
                file_name=pdf_path.name,
                sha256=digest,
                status="rejected",
                rejection_codes=["MALFORMED_PDF"],
                metrics=CapabilityMetrics(
                    page_count=1,
                    total_text_characters=0,
                    text_page_ratio=0,
                    raster_dominant_page_ratio=0,
                    latin_letter_ratio=0,
                    english_function_word_ratio=0,
                ),
                pages=[],
            )

        if document.needs_pass:
            return PDFCapabilityReport(
                file_name=pdf_path.name,
                sha256=digest,
                status="rejected",
                rejection_codes=["ENCRYPTED_PDF"],
                metrics=CapabilityMetrics(
                    page_count=max(1, len(document)),
                    total_text_characters=0,
                    text_page_ratio=0,
                    raster_dominant_page_ratio=0,
                    latin_letter_ratio=0,
                    english_function_word_ratio=0,
                ),
                pages=[],
            )

        for page_index, page in enumerate(document):
            text = page.get_text("text")
            meaningful = "".join(character for character in text if not character.isspace())
            all_text.append(text)
            image_area = 0.0
            for info in page.get_image_info(xrefs=True):
                rect = fitz.Rect(info["bbox"])
                image_area += max(0.0, rect.width) * max(0.0, rect.height)
            page_area = max(1.0, page.rect.width * page.rect.height)
            coverage = min(1.0, image_area / page_area)
            pages.append(
                PageCapability(
                    page_number=page_index + 1,
                    text_characters=len(meaningful),
                    image_coverage_ratio=coverage,
                )
            )

        total_text = "\n".join(all_text)
        text_chars = sum(page.text_characters for page in pages)
        text_page_ratio = sum(page.text_characters >= 80 for page in pages) / max(1, len(pages))
        raster_ratio = sum(page.image_coverage_ratio >= 0.5 for page in pages) / max(1, len(pages))
        letters = [character for character in total_text if character.isalpha()]
        latin_letters = sum("a" <= character.lower() <= "z" for character in letters)
        latin_ratio = latin_letters / max(1, len(letters))
        words = re.findall(r"[A-Za-z]+", total_text.lower())
        english_hits = sum(word in ENGLISH_FUNCTION_WORDS for word in words)
        english_ratio = english_hits / max(1, len(words))

        if text_chars < self.minimum_total_characters or text_page_ratio < self.minimum_text_page_ratio:
            rejection_codes.append("NO_TEXT_LAYER")
        if raster_ratio >= 0.5:
            rejection_codes.append("SCANNED_PDF")
        if (
            text_chars >= self.minimum_total_characters
            and (latin_ratio < self.minimum_latin_ratio or english_ratio < self.minimum_english_word_ratio)
        ):
            rejection_codes.append("NON_ENGLISH_PDF")

        metrics = CapabilityMetrics(
            page_count=max(1, len(pages)),
            total_text_characters=text_chars,
            text_page_ratio=text_page_ratio,
            raster_dominant_page_ratio=raster_ratio,
            latin_letter_ratio=latin_ratio,
            english_function_word_ratio=english_ratio,
        )
        return PDFCapabilityReport(
            file_name=pdf_path.name,
            sha256=digest,
            status="rejected" if rejection_codes else "supported",
            rejection_codes=rejection_codes,
            metrics=metrics,
            pages=pages,
        )

    def extract(self, pdf_path: Path, paper_id: PaperId, output_dir: Path) -> DocumentIR:
        report = self.detect(pdf_path)
        if report.status != "supported":
            raise UnsupportedPDFError(report)

        output_dir.mkdir(parents=True, exist_ok=True)
        assets_dir = output_dir / "assets"
        assets_dir.mkdir(parents=True, exist_ok=True)
        document = fitz.open(pdf_path)
        page_dicts = [page.get_text("dict", sort=True) for page in document]
        body_font_size = _body_font_size(page_dicts)
        candidates = _collect_blocks(page_dicts, body_font_size)
        title_candidate = _find_title_candidate(candidates, body_font_size)
        _classify_blocks(candidates, title_candidate, body_font_size)
        sections = _assign_sections(candidates)

        blocks: list[SourceBlock] = []
        source_refs: list[SourceReference] = []
        equations: list[SourceEquation] = []
        assets: list[SourceAsset] = []
        global_order = 0
        block_number_by_page: dict[int, int] = {}
        asset_number = 0

        for candidate in candidates:
            global_order += 1
            block_number_by_page[candidate.page] = block_number_by_page.get(candidate.page, 0) + 1
            block_id = f"srcblk_p{candidate.page:03d}_{block_number_by_page[candidate.page]:04d}"
            block = SourceBlock(
                block_id=block_id,
                block_type=candidate.block_type,
                page=candidate.page,
                section_id=candidate.section_id,
                text=candidate.text,
                bbox=_bbox(candidate.bbox),
                reading_order=global_order,
            )
            blocks.append(block)
            source_refs.append(
                SourceReference(
                    source_ref_id=f"src_p{candidate.page:03d}_b{block_number_by_page[candidate.page]:04d}",
                    source_type="text_span",
                    locator=SourceLocator(
                        page=candidate.page,
                        block_id=block_id,
                        char_start=0,
                        char_end=len(candidate.text),
                        bbox=_bbox(candidate.bbox),
                    ),
                    quote=candidate.text,
                    checksum=_text_checksum(candidate.text),
                )
            )

            caption_kind = _caption_kind(candidate.text)
            if caption_kind:
                asset_number += 1
                asset_type = caption_kind
                asset_id = f"ast_{asset_type}_{asset_number:03d}"
                page = document[candidate.page - 1]
                crop = _asset_crop(page, candidate.bbox, asset_type, candidate.text)
                relative_path = Path("assets") / f"{asset_id}.png"
                pixmap = page.get_pixmap(matrix=fitz.Matrix(2, 2), clip=crop, alpha=False)
                pixmap.save(output_dir / relative_path)
                assets.append(
                    SourceAsset(
                        asset_id=asset_id,
                        asset_type=asset_type,
                        page=candidate.page,
                        caption=candidate.text,
                        path=relative_path.as_posix(),
                        bbox=_bbox(crop),
                    )
                )
                source_refs.append(
                    SourceReference(
                        source_ref_id=f"src_{asset_id}",
                        source_type=asset_type,
                        locator=SourceLocator(
                            page=candidate.page,
                            asset_id=asset_id,
                            bbox=_bbox(crop),
                        ),
                        quote=candidate.text,
                        checksum=_text_checksum(candidate.text),
                    )
                )

        for page_number, (page_dict, page) in enumerate(zip(page_dicts, document), start=1):
            for equation_number, (
                equation_text,
                equation_bbox,
                equation_label,
            ) in enumerate(_extract_page_equations(page_dict, page.rect), start=1):
                equation_id = f"seq_p{page_number:03d}_{equation_number:03d}"
                equations.append(
                    SourceEquation(
                        source_equation_id=equation_id,
                        page=page_number,
                        label=equation_label,
                        representation="pdf_text",
                        raw_text=equation_text,
                        latex=None,
                        bbox=_bbox(equation_bbox),
                    )
                )
                source_refs.append(
                    SourceReference(
                        source_ref_id=f"src_{equation_id}",
                        source_type="equation",
                        locator=SourceLocator(
                            page=page_number,
                            source_equation_id=equation_id,
                            bbox=_bbox(equation_bbox),
                        ),
                        quote=equation_text,
                        checksum=_text_checksum(equation_text),
                    )
                )

        title = (document.metadata.get("title") or "").strip()
        if not title and title_candidate is not None:
            title = title_candidate.text
        if not title:
            title = pdf_path.stem
        author = (document.metadata.get("author") or "").strip()
        warnings: list[str] = []
        if not author:
            warnings.append("PDF metadata does not provide authors; deterministic inference was not attempted.")
        if not equations:
            warnings.append("No display equations were detected from the PDF text layer.")
        if not assets:
            warnings.append("No caption-anchored figures or tables were detected.")

        abstract = _extract_abstract(blocks, sections)
        return DocumentIR(
            schema_version="1.0.0",
            artifact_revision=1,
            paper_id=paper_id,
            source=DocumentSource(
                file_name=pdf_path.name,
                sha256=report.sha256,
                language="en",
                input_type="text_pdf",
                page_count=len(document),
            ),
            metadata=PaperMetadata(
                title=title,
                authors=[author] if author else [],
                abstract=abstract,
            ),
            pages=[
                PageInfo(page_number=index + 1, width=page.rect.width, height=page.rect.height)
                for index, page in enumerate(document)
            ],
            sections=sections,
            blocks=blocks,
            equations=equations,
            assets=assets,
            source_refs=source_refs,
            warnings=warnings,
        )


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return f"sha256:{digest.hexdigest()}"


def _text_checksum(text: str) -> str:
    return f"sha256:{hashlib.sha256(text.encode('utf-8')).hexdigest()}"


def _bbox(rect: fitz.Rect) -> BoundingBox:
    return BoundingBox(x0=rect.x0, y0=rect.y0, x1=rect.x1, y1=rect.y1)


def _line_text(line: dict[str, Any]) -> str:
    return "".join(span.get("text", "") for span in line.get("spans", [])).strip()


def _block_text(block: dict[str, Any]) -> str:
    lines = [_line_text(line) for line in block.get("lines", [])]
    return " ".join(line for line in lines if line).strip()


def _body_font_size(page_dicts: Iterable[dict[str, Any]]) -> float:
    sizes: list[float] = []
    for page in page_dicts:
        for block in page.get("blocks", []):
            if block.get("type") != 0:
                continue
            for line in block.get("lines", []):
                for span in line.get("spans", []):
                    if len(span.get("text", "").strip()) >= 4:
                        sizes.append(float(span.get("size", 0)))
    return median(sizes) if sizes else 10.0


def _looks_like_heading(text: str, max_font_size: float, bold: bool, body_font_size: float) -> bool:
    stripped = text.strip()
    if not HEADING_RE.match(stripped) or len(stripped) > 180:
        return False
    numbered = bool(re.match(r"^(?:[0-9]+|[IVXLCDM]+)[.)]?\s+", stripped))
    all_caps = stripped.upper() == stripped and any(character.isalpha() for character in stripped)
    styled = bold and max_font_size >= body_font_size * 1.03
    return numbered or all_caps or styled or stripped.lower() == "abstract"


def _collect_blocks(
    page_dicts: list[dict[str, Any]], body_font_size: float
) -> list[_BlockCandidate]:
    candidates: list[_BlockCandidate] = []
    for page_index, page_dict in enumerate(page_dicts):
        for block in page_dict.get("blocks", []):
            if block.get("type") != 0:
                continue
            text = _block_text(block)
            if not text:
                continue
            spans = [span for line in block.get("lines", []) for span in line.get("spans", [])]
            max_size = max((float(span.get("size", 0)) for span in spans), default=0.0)
            bold = any("bold" in span.get("font", "").lower() for span in spans)
            lines = block.get("lines", [])
            first_line_text = _line_text(lines[0]) if lines else ""
            first_spans = lines[0].get("spans", []) if lines else []
            first_max_size = max(
                (float(span.get("size", 0)) for span in first_spans), default=max_size
            )
            first_bold = any("bold" in span.get("font", "").lower() for span in first_spans)
            abstract_match = re.match(r"^\s*Abstract\s*[—-]\s*(.+)$", first_line_text, re.IGNORECASE)
            if abstract_match:
                first_rect = fitz.Rect(lines[0]["bbox"])
                candidates.append(
                    _BlockCandidate(
                        page=page_index + 1,
                        text="Abstract",
                        bbox=first_rect,
                        max_font_size=max_size,
                        bold=True,
                        lines=[],
                        block_type="heading",
                    )
                )
                remainder_lines = lines[1:]
                remainder_text = " ".join(
                    [abstract_match.group(1)] + [_line_text(line) for line in remainder_lines]
                ).strip()
                if remainder_text:
                    remainder_bbox = fitz.Rect(block["bbox"])
                    candidates.append(
                        _BlockCandidate(
                            page=page_index + 1,
                            text=remainder_text,
                            bbox=remainder_bbox,
                            max_font_size=max_size,
                            bold=bold,
                            lines=remainder_lines,
                        )
                    )
                continue
            if len(lines) > 1 and _looks_like_heading(
                first_line_text, first_max_size, first_bold, body_font_size
            ):
                first_rect = fitz.Rect(lines[0]["bbox"])
                candidates.append(
                    _BlockCandidate(
                        page=page_index + 1,
                        text=first_line_text,
                        bbox=first_rect,
                        max_font_size=max_size,
                        bold=bold,
                        lines=[lines[0]],
                        block_type="heading",
                    )
                )
                remainder_lines = lines[1:]
                remainder_text = " ".join(_line_text(line) for line in remainder_lines).strip()
                if remainder_text:
                    remainder_rect = fitz.Rect(remainder_lines[0]["bbox"])
                    for line in remainder_lines[1:]:
                        remainder_rect |= fitz.Rect(line["bbox"])
                    candidates.append(
                        _BlockCandidate(
                            page=page_index + 1,
                            text=remainder_text,
                            bbox=remainder_rect,
                            max_font_size=max_size,
                            bold=bold,
                            lines=remainder_lines,
                        )
                    )
                continue
            candidates.append(
                _BlockCandidate(
                    page=page_index + 1,
                    text=text,
                    bbox=fitz.Rect(block["bbox"]),
                    max_font_size=max_size,
                    bold=bold,
                    lines=lines,
                )
            )
    ordered: list[_BlockCandidate] = []
    for page_index, page_dict in enumerate(page_dicts, start=1):
        page_candidates = [item for item in candidates if item.page == page_index]
        page_width = float(page_dict.get("width", 612.0))
        page_height = float(page_dict.get("height", 792.0))
        ordered.extend(
            _reading_order_for_page(
                page_candidates,
                page_width=page_width,
                page_height=page_height,
                body_font_size=body_font_size,
            )
        )
    return ordered


def _reading_order_for_page(
    candidates: list[_BlockCandidate],
    *,
    page_width: float,
    page_height: float,
    body_font_size: float,
) -> list[_BlockCandidate]:
    """Apply a deterministic, geometry-only reading order to a PDF page.

    PyMuPDF's sorted block order is top-to-bottom, which interleaves two-column
    papers.  This lightweight XY-cut treats wide, center-crossing blocks as band
    separators and reads the remaining blocks left-column then right-column.
    Small bottom-of-page notes are moved after the main flow.
    """

    if len(candidates) < 4:
        return sorted(candidates, key=lambda item: (item.bbox.y0, item.bbox.x0))

    center = page_width / 2
    column_tolerance = page_width * 0.025
    left = [item for item in candidates if item.bbox.x1 <= center + column_tolerance]
    right = [item for item in candidates if item.bbox.x0 >= center - column_tolerance]
    if len(left) < 2 or len(right) < 2:
        return sorted(candidates, key=lambda item: (item.bbox.y0, item.bbox.x0))

    footnotes = [
        item
        for item in candidates
        if item.bbox.y0 >= page_height * 0.55
        and item.max_font_size <= body_font_size * 0.86
        and item.block_type not in {"heading", "caption", "title"}
    ]
    footnote_ids = {id(item) for item in footnotes}
    main = [item for item in candidates if id(item) not in footnote_ids]
    spanning = [
        item
        for item in main
        if item.bbox.x0 < center - page_width * 0.08
        and item.bbox.x1 > center + page_width * 0.08
    ]
    spanning_ids = {id(item) for item in spanning}
    column_items = [item for item in main if id(item) not in spanning_ids]

    def order_columns(items: list[_BlockCandidate]) -> list[_BlockCandidate]:
        def order_key(item: _BlockCandidate) -> tuple[float, int, float]:
            structural_priority = 0 if item.block_type in {"title", "heading"} else 1
            return (round(item.bbox.y0, 1), structural_priority, item.bbox.x0)

        left_items = [item for item in items if item.bbox.x0 < center]
        right_items = [item for item in items if item.bbox.x0 >= center]
        return sorted(left_items, key=order_key) + sorted(right_items, key=order_key)

    result: list[_BlockCandidate] = []
    remaining = list(column_items)
    band_floor = 0.0
    for separator in sorted(spanning, key=lambda item: (item.bbox.y0, item.bbox.x0)):
        band = [
            item
            for item in remaining
            if band_floor <= item.bbox.y0 < separator.bbox.y0
        ]
        result.extend(order_columns(band))
        band_ids = {id(item) for item in band}
        remaining = [item for item in remaining if id(item) not in band_ids]
        result.append(separator)
        band_floor = max(band_floor, separator.bbox.y1)
    result.extend(order_columns(remaining))
    result.extend(sorted(footnotes, key=lambda item: (item.bbox.y0, item.bbox.x0)))
    return result


def _find_title_candidate(
    candidates: list[_BlockCandidate], body_font_size: float
) -> _BlockCandidate | None:
    options = [
        item
        for item in candidates
        if item.page == 1
        and item.bbox.y0 < 260
        and 10 <= len(item.text) <= 400
        and item.max_font_size >= body_font_size * 1.35
    ]
    return max(options, key=lambda item: (item.max_font_size, item.bbox.width), default=None)


def _classify_blocks(
    candidates: list[_BlockCandidate],
    title_candidate: _BlockCandidate | None,
    body_font_size: float,
) -> None:
    for candidate in candidates:
        if candidate is title_candidate:
            candidate.block_type = "title"
        elif _caption_kind(candidate.text):
            candidate.block_type = "caption"
        elif _looks_like_heading(
            candidate.text, candidate.max_font_size, candidate.bold, body_font_size
        ):
            candidate.block_type = "heading"
        elif (
            candidate.max_font_size >= body_font_size * 1.35
            and candidate.bold
            and len(candidate.text) <= 120
        ):
            candidate.block_type = "heading"
        elif re.match(r"^\s*(?:[•◦▪]|[-*]\s|[0-9]+[.)]\s)", candidate.text):
            candidate.block_type = "list_item"


def _assign_sections(candidates: list[_BlockCandidate]) -> list[SourceSection]:
    section_records: list[dict[str, Any]] = []
    current: dict[str, Any] | None = None
    for candidate in candidates:
        if candidate.block_type == "heading":
            current = {
                "section_id": f"srcsec_{len(section_records) + 1:03d}",
                "title": candidate.text,
                "page_start": candidate.page,
                "page_end": candidate.page,
            }
            section_records.append(current)
        if current is not None:
            candidate.section_id = current["section_id"]
            current["page_end"] = max(current["page_end"], candidate.page)
    if not section_records:
        section_records.append(
            {
                "section_id": "srcsec_001",
                "title": "Document",
                "page_start": 1,
                "page_end": max(item.page for item in candidates),
            }
        )
        for candidate in candidates:
            candidate.section_id = "srcsec_001"
    return [
        SourceSection(
            section_id=record["section_id"],
            title=record["title"],
            level=1,
            page_start=record["page_start"],
            page_end=record["page_end"],
        )
        for record in section_records
    ]


def _is_equation_fragment(line: dict[str, Any], text: str) -> bool:
    if not text or len(text) > 220 or re.fullmatch(r"\([0-9]{1,3}\)", text):
        return False
    if text in {",", ".", ";", ":"}:
        return False
    if text.lower().startswith(PROSE_EQUATION_LEADERS):
        return False
    spans = line.get("spans", [])
    fonts = [span.get("font", "").lower() for span in spans]
    math_spans = sum(any(marker in font for marker in MATH_FONT_MARKERS) for font in fonts)
    math_ratio = math_spans / max(1, len(fonts))
    operator_count = sum(character in MATH_OPERATORS for character in text)
    prose_words = re.findall(r"[A-Za-z]{3,}", text)
    math_tokens = re.findall(r"(?:[A-Za-z]|[0-9]+|[=∑∫≤≥≈→←±×÷∂∇∞∥])", text)
    token_count = max(1, len(re.findall(r"\S+", text)))
    math_density = len(math_tokens) / token_count
    return (
        len(prose_words) <= 3
        and math_density >= 0.45
        and ((math_ratio >= 0.4 and operator_count >= 1) or operator_count >= 2)
    )


def _is_labeled_equation_fragment(line: dict[str, Any], text: str) -> bool:
    """Use a looser rule only near an explicit equation number."""

    if not text or len(text) > 180 or text.lower().startswith(PROSE_EQUATION_LEADERS):
        return False
    if re.fullmatch(r"\([0-9]{1,3}\)", text):
        return False
    spans = line.get("spans", [])
    fonts = [span.get("font", "").lower() for span in spans]
    has_math_font = any(any(marker in font for marker in MATH_FONT_MARKERS) for font in fonts)
    has_operator = any(character in MATH_OPERATORS for character in text)
    prose_words = re.findall(r"[A-Za-z]{3,}", text)
    return len(prose_words) <= 4 and (has_math_font or has_operator)


def _is_display_equation(line: dict[str, Any], text: str, page_rect: fitz.Rect) -> bool:
    if not text or len(text) > 320:
        return False
    bbox = fitz.Rect(line["bbox"])
    centered_or_indented = bbox.x0 > page_rect.width * 0.12 and bbox.x1 < page_rect.width * 0.94
    return centered_or_indented and _is_equation_fragment(line, text)


def _extract_page_equations(
    page_dict: dict[str, Any], page_rect: fitz.Rect
) -> list[tuple[str, fitz.Rect, str | None]]:
    results: list[tuple[str, fitz.Rect, str | None]] = []
    consumed: set[int] = set()
    lines = [
        line
        for block in page_dict.get("blocks", [])
        if block.get("type") == 0
        for line in block.get("lines", [])
        if _line_text(line)
    ]
    texts = [_line_text(line) for line in lines]

    for index, text in enumerate(texts):
        inline_label = EQUATION_LABEL_RE.search(text)
        if not inline_label:
            continue
        equation_text = text[: inline_label.start()].strip()
        if equation_text and _is_equation_fragment(lines[index], equation_text):
            results.append(
                (equation_text, fitz.Rect(lines[index]["bbox"]), inline_label.group(1))
            )
            consumed.add(index)

    for index, text in enumerate(texts):
        if index in consumed:
            continue
        label_match = re.fullmatch(r"\(([0-9]{1,3})\)", text)
        if not label_match:
            continue
        label_bbox = fitz.Rect(lines[index]["bbox"])
        fragments = []
        for candidate_index, (candidate_line, candidate_text) in enumerate(zip(lines, texts)):
            if candidate_index == index or candidate_index in consumed:
                continue
            candidate_bbox = fitz.Rect(candidate_line["bbox"])
            center_distance = abs(
                (candidate_bbox.y0 + candidate_bbox.y1) / 2
                - (label_bbox.y0 + label_bbox.y1) / 2
            )
            is_near_label = center_distance <= 36
            is_left_of_label = candidate_bbox.x0 < label_bbox.x0 and candidate_bbox.x1 <= label_bbox.x1
            if label_bbox.x0 > page_rect.width * 0.85:
                is_left_of_label = is_left_of_label and candidate_bbox.x0 > page_rect.width * 0.48
            if is_near_label and is_left_of_label and _is_labeled_equation_fragment(
                candidate_line, candidate_text
            ):
                fragments.append(candidate_index)
        if not fragments:
            consumed.add(index)
            continue
        fragments.sort(key=lambda item: (fitz.Rect(lines[item]["bbox"]).y0, fitz.Rect(lines[item]["bbox"]).x0))
        equation_text = _clean_equation_text(" ".join(texts[item] for item in fragments))
        equation_bbox = fitz.Rect(lines[fragments[0]]["bbox"])
        for item in fragments[1:] + [index]:
            equation_bbox |= fitz.Rect(lines[item]["bbox"])
        results.append((equation_text, equation_bbox, label_match.group(1)))
        consumed.update(fragments)
        consumed.add(index)

    strong_unlabeled: list[int] = []
    for index, (line, text) in enumerate(zip(lines, texts)):
        if index in consumed:
            continue
        operator_count = sum(character in MATH_OPERATORS for character in text)
        has_equation_anchor = "=" in text or any(
            character in text for character in "∑∫∂∇"
        )
        starts_with_orphan_operator = text.lstrip().startswith(("=", "+", "/"))
        if (
            has_equation_anchor
            and not starts_with_orphan_operator
            and _is_display_equation(line, text, page_rect)
            and operator_count >= 2
        ):
            strong_unlabeled.append(index)
    for index in strong_unlabeled:
        text = texts[index]
        results.append((text, fitz.Rect(lines[index]["bbox"]), None))

    results.sort(key=lambda item: (item[1].y0, item[1].x0))
    return results


def _clean_equation_text(text: str) -> str:
    """Remove deterministic prose lead-ins while preserving PDF-extracted symbols."""

    if ":" in text:
        candidate = text.rsplit(":", 1)[-1].strip()
        if candidate and any(character in MATH_OPERATORS for character in candidate):
            text = candidate
    return " ".join(text.split())


def _asset_crop(page: fitz.Page, caption_bbox: fitz.Rect, asset_type: str, caption: str) -> fitz.Rect:
    wide_caption = caption_bbox.width >= page.rect.width * 0.62
    if wide_caption:
        x0, x1 = 36.0, page.rect.width - 36.0
    else:
        column_padding = 8.0
        x0 = max(24.0, caption_bbox.x0 - column_padding)
        x1 = min(page.rect.width - 24.0, caption_bbox.x1 + column_padding)

    if asset_type == "figure":
        image_candidates = []
        for block in page.get_text("dict", sort=True).get("blocks", []):
            if block.get("type") != 1:
                continue
            rect = fitz.Rect(block["bbox"])
            overlap = max(0.0, min(rect.x1, x1) - max(rect.x0, x0))
            if rect.y1 <= caption_bbox.y0 + 8 and caption_bbox.y0 - rect.y1 <= 300 and overlap > 0:
                image_candidates.append(rect)
        # Composite scientific figures are often mostly vector paths with many
        # small embedded raster tiles. Selecting the raster nearest the caption
        # captures only the bottom strip. For wide figures, accept a full-width
        # vector boundary only when it ends next to the caption and materially
        # expands the crop; this avoids swallowing unrelated page drawings.
        nearest_image = max(image_candidates, key=lambda rect: rect.y1) if image_candidates else None
        drawing_candidates = []
        if wide_caption:
            for drawing in page.get_drawings():
                rect = fitz.Rect(drawing["rect"])
                overlap = max(0.0, min(rect.x1, x1) - max(rect.x0, x0))
                if (
                    rect.width >= (x1 - x0) * 0.7
                    and rect.height >= 40
                    and rect.y1 <= caption_bbox.y0 + 8
                    and caption_bbox.y0 - rect.y1 <= 36
                    and overlap > 0
                ):
                    drawing_candidates.append(rect)
        visual = nearest_image
        if drawing_candidates:
            drawing = max(drawing_candidates, key=lambda rect: rect.width * rect.height)
            if nearest_image is None or drawing.y0 < nearest_image.y0 - 40:
                visual = drawing
        if visual is not None:
            # Captions remain metadata for the source inspector and should not
            # be baked into the poster-facing visual crop.
            visual_bottom = min(caption_bbox.y0 - 2, max(visual.y1, caption_bbox.y0 - 4))
            crop = fitz.Rect(min(x0, visual.x0), visual.y0, max(x1, visual.x1), visual_bottom)
        else:
            crop = fitz.Rect(x0, max(32.0, caption_bbox.y0 - 230.0), x1, caption_bbox.y0 - 2)
    else:
        if caption_bbox.height >= 90 or len(caption) >= 500:
            crop = fitz.Rect(x0, caption_bbox.y0, x1, caption_bbox.y1)
        else:
            crop = fitz.Rect(x0, caption_bbox.y0, x1, min(page.rect.height - 32.0, caption_bbox.y1 + 220.0))
    return crop & page.rect


def _caption_kind(text: str) -> str | None:
    if FIGURE_CAPTION_RE.match(text):
        return "figure"
    if TABLE_CAPTION_RE.match(text) or _looks_like_ieee_table_caption(text):
        return "table"
    return None


def _looks_like_ieee_table_caption(text: str) -> bool:
    """Recognize IEEE's ``TABLE II / ALL-CAPS TITLE`` convention conservatively.

    PyMuPDF sometimes merges the caption and table body into one text block, so
    requiring the entire block to be uppercase loses valid tables. Checking only
    the leading title window still excludes prose such as "Table II summarizes".
    """

    match = IEEE_TABLE_CAPTION_RE.match(text.strip())
    if match is None:
        return False
    title_window = match.group(2)[:160]
    letters = [character for character in title_window if character.isalpha()]
    if len(letters) < 5:
        return False
    uppercase_ratio = sum(character.isupper() for character in letters) / len(letters)
    return uppercase_ratio >= 0.8


def _extract_abstract(
    blocks: list[SourceBlock], sections: list[SourceSection]
) -> str | None:
    abstract_sections = {
        section.section_id for section in sections if section.title.strip().lower() == "abstract"
    }
    if not abstract_sections:
        return None
    parts = [
        block.text
        for block in blocks
        if block.section_id in abstract_sections and block.block_type not in {"heading", "title"}
        and not block.text.lower().startswith("index terms")
    ]
    abstract = " ".join(parts).strip()
    return abstract or None
