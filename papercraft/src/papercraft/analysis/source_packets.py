"""Build minimal, source-addressable model inputs from DocumentIR."""

from __future__ import annotations

import base64
from dataclasses import dataclass
from pathlib import Path

import fitz

from papercraft.models import DocumentIR
from papercraft.providers import ImageInput


@dataclass(frozen=True)
class SourcePacket:
    text: str
    images: list[ImageInput]
    source_ref_ids: frozenset[str]


def build_source_packet(
    document_ir: DocumentIR,
    *,
    asset_root: Path | None = None,
    include_source_types: set[str] | None = None,
    include_pages: set[int] | None = None,
    preferred_asset_ids: tuple[str, ...] = (),
    page_image_pages: tuple[int, ...] = (),
    max_characters: int = 80_000,
    max_images: int = 4,
) -> SourcePacket:
    """Serialize only verifiable references, never the full original PDF."""

    allowed = include_source_types or {"text_span", "equation", "figure", "table"}
    lines: list[str] = []
    selected_ids: set[str] = set()
    size = 0
    for ref in document_ir.source_refs:
        if ref.source_type not in allowed:
            continue
        if include_pages is not None and ref.locator.page not in include_pages:
            continue
        line = (
            f"[{ref.source_ref_id} | page {ref.locator.page} | {ref.source_type}]\n"
            f"{ref.quote}\n"
        )
        if size + len(line) > max_characters:
            break
        lines.append(line)
        selected_ids.add(ref.source_ref_id)
        size += len(line)

    images: list[ImageInput] = []
    if asset_root is not None:
        ranked_assets = sorted(
            (
                [item for item in document_ir.assets if item.asset_id in preferred_asset_ids]
                if preferred_asset_ids
                else document_ir.assets
            ),
            key=lambda item: (
                preferred_asset_ids.index(item.asset_id)
                if item.asset_id in preferred_asset_ids
                else len(preferred_asset_ids),
                item.page,
            ),
        )
        for asset in ranked_assets:
            if include_pages is not None and asset.page not in include_pages:
                continue
            path = asset_root / asset.path
            if not path.is_file():
                continue
            media_type = "image/png" if path.suffix.lower() == ".png" else "image/jpeg"
            images.append(
                ImageInput(
                    media_type=media_type,
                    base64_data=base64.b64encode(path.read_bytes()).decode("ascii"),
                    label=f"{asset.asset_id}: {asset.caption}",
                )
            )
            if len(images) >= max_images:
                break
        pdf_path = asset_root / "source.pdf"
        if pdf_path.is_file() and len(images) < max_images:
            cache = asset_root / ".model_inputs"
            cache.mkdir(parents=True, exist_ok=True)
            with fitz.open(pdf_path) as pdf:
                for page_number in page_image_pages:
                    if len(images) >= max_images or not 1 <= page_number <= len(pdf):
                        break
                    target = cache / f"page_{page_number:03d}.jpg"
                    if not target.is_file():
                        pixmap = pdf[page_number - 1].get_pixmap(
                            matrix=fitz.Matrix(1.55, 1.55), alpha=False
                        )
                        pixmap.save(target, jpg_quality=82)
                    images.append(
                        ImageInput(
                            media_type="image/jpeg",
                            base64_data=base64.b64encode(target.read_bytes()).decode("ascii"),
                            label=f"Rendered source page {page_number}",
                        )
                    )
    return SourcePacket("\n".join(lines), images, frozenset(selected_ids))
