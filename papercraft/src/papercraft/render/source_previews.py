"""Deterministic PDF crops used instead of damaged formula/table text."""

from __future__ import annotations

from pathlib import Path

import fitz

from papercraft.models import DocumentIR


def generate_source_previews(
    document_ir: DocumentIR,
    pdf_path: Path,
    asset_dir: Path,
) -> list[Path]:
    """Render source-addressable equation crops without changing DocumentIR 1.0."""

    if not pdf_path.is_file():
        return []
    asset_dir.mkdir(parents=True, exist_ok=True)
    equations = {item.source_equation_id: item for item in document_ir.equations}
    generated: list[Path] = []
    with fitz.open(pdf_path) as pdf:
        for ref in document_ir.source_refs:
            if ref.source_type != "equation" or ref.locator.source_equation_id is None:
                continue
            equation = equations.get(ref.locator.source_equation_id)
            if equation is None:
                continue
            bbox = ref.locator.bbox or equation.bbox
            page = pdf[ref.locator.page - 1]
            padding_x = max(8.0, bbox.x1 - bbox.x0) * 0.08
            padding_y = max(5.0, bbox.y1 - bbox.y0) * 0.45
            clip = fitz.Rect(
                max(0, bbox.x0 - padding_x),
                max(0, bbox.y0 - padding_y),
                min(page.rect.width, bbox.x1 + padding_x),
                min(page.rect.height, bbox.y1 + padding_y),
            )
            target = asset_dir / f"preview_{ref.source_ref_id}.png"
            page.get_pixmap(matrix=fitz.Matrix(2.4, 2.4), clip=clip, alpha=False).save(target)
            generated.append(target)
    return generated
