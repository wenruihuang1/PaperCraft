"""Normalized, source-addressable representation of an English text PDF."""

from __future__ import annotations

from typing import Literal

from pydantic import Field, PositiveFloat, PositiveInt, model_validator

from papercraft.models.common import (
    PaperId,
    Sha256,
    SourceAssetId,
    SourceBlockId,
    SourceEquationId,
    SourceRefId,
    SourceSectionId,
    StrictModel,
    ensure_unique,
)


class DocumentSource(StrictModel):
    file_name: str = Field(min_length=1)
    sha256: Sha256
    language: Literal["en"]
    input_type: Literal["text_pdf"]
    page_count: PositiveInt


class PaperMetadata(StrictModel):
    title: str = Field(min_length=1)
    authors: list[str] = Field(default_factory=list)
    abstract: str | None = None


class BoundingBox(StrictModel):
    x0: float
    y0: float
    x1: float
    y1: float

    @model_validator(mode="after")
    def ordered(self) -> "BoundingBox":
        if self.x1 <= self.x0 or self.y1 <= self.y0:
            raise ValueError("bbox must have positive width and height")
        return self


class PageInfo(StrictModel):
    page_number: PositiveInt
    width: PositiveFloat
    height: PositiveFloat


class SourceSection(StrictModel):
    section_id: SourceSectionId
    title: str = Field(min_length=1)
    level: PositiveInt
    page_start: PositiveInt
    page_end: PositiveInt

    @model_validator(mode="after")
    def page_order(self) -> "SourceSection":
        if self.page_end < self.page_start:
            raise ValueError("section page_end must not precede page_start")
        return self


class SourceBlock(StrictModel):
    block_id: SourceBlockId
    block_type: Literal["title", "heading", "paragraph", "list_item", "caption"]
    page: PositiveInt
    section_id: SourceSectionId | None = None
    text: str = Field(min_length=1)
    bbox: BoundingBox
    reading_order: int = Field(ge=0)


class SourceEquation(StrictModel):
    source_equation_id: SourceEquationId
    page: PositiveInt
    label: str | None = None
    representation: Literal["pdf_text", "latex"]
    raw_text: str = Field(min_length=1)
    latex: str | None = None
    bbox: BoundingBox

    @model_validator(mode="after")
    def representation_is_honest(self) -> "SourceEquation":
        if self.representation == "latex" and not self.latex:
            raise ValueError("latex representation requires latex")
        return self


class SourceAsset(StrictModel):
    asset_id: SourceAssetId
    asset_type: Literal["figure", "table"]
    page: PositiveInt
    caption: str = Field(min_length=1)
    path: str = Field(min_length=1)
    bbox: BoundingBox


class SourceLocator(StrictModel):
    page: PositiveInt
    block_id: SourceBlockId | None = None
    source_equation_id: SourceEquationId | None = None
    asset_id: SourceAssetId | None = None
    char_start: int | None = Field(default=None, ge=0)
    char_end: int | None = Field(default=None, ge=0)
    bbox: BoundingBox | None = None


class SourceReference(StrictModel):
    source_ref_id: SourceRefId
    source_type: Literal["text_span", "equation", "figure", "table", "caption"]
    locator: SourceLocator
    quote: str = Field(min_length=1)
    checksum: Sha256

    @model_validator(mode="after")
    def locator_matches_type(self) -> "SourceReference":
        locator = self.locator
        if self.source_type == "text_span" and locator.block_id is None:
            raise ValueError("text_span source requires block_id")
        if self.source_type == "equation" and locator.source_equation_id is None:
            raise ValueError("equation source requires source_equation_id")
        if self.source_type in {"figure", "table", "caption"} and locator.asset_id is None:
            raise ValueError(f"{self.source_type} source requires asset_id")
        if (locator.char_start is None) != (locator.char_end is None):
            raise ValueError("char_start and char_end must be provided together")
        if locator.char_start is not None and locator.char_end <= locator.char_start:
            raise ValueError("char_end must be greater than char_start")
        return self


class DocumentIR(StrictModel):
    # DocumentIR 1.0 is the frozen Stage C input contract. A later incompatible
    # contract must use a new explicit Literal rather than silently accepting it.
    schema_version: Literal["1.0.0"]
    artifact_revision: PositiveInt
    paper_id: PaperId
    source: DocumentSource
    metadata: PaperMetadata
    pages: list[PageInfo] = Field(min_length=1)
    sections: list[SourceSection]
    blocks: list[SourceBlock] = Field(min_length=1)
    equations: list[SourceEquation] = Field(default_factory=list)
    assets: list[SourceAsset] = Field(default_factory=list)
    source_refs: list[SourceReference] = Field(min_length=1)
    warnings: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def local_integrity(self) -> "DocumentIR":
        ensure_unique((page.page_number for page in self.pages), "page_number")
        ensure_unique((section.section_id for section in self.sections), "source section ID")
        ensure_unique((block.block_id for block in self.blocks), "source block ID")
        ensure_unique((item.source_equation_id for item in self.equations), "source equation ID")
        ensure_unique((asset.asset_id for asset in self.assets), "source asset ID")
        ensure_unique((ref.source_ref_id for ref in self.source_refs), "source reference ID")

        page_numbers = {page.page_number for page in self.pages}
        if page_numbers != set(range(1, self.source.page_count + 1)):
            raise ValueError("pages must cover 1..page_count exactly")

        section_ids = {section.section_id for section in self.sections}
        blocks_by_id = {block.block_id: block for block in self.blocks}
        equations_by_id = {item.source_equation_id: item for item in self.equations}
        assets_by_id = {asset.asset_id: asset for asset in self.assets}
        block_ids = set(blocks_by_id)
        equation_ids = set(equations_by_id)
        asset_ids = set(assets_by_id)

        for block in self.blocks:
            if block.page not in page_numbers:
                raise ValueError(f"block {block.block_id} uses unknown page")
            if block.section_id is not None and block.section_id not in section_ids:
                raise ValueError(f"block {block.block_id} uses unknown section")
        for ref in self.source_refs:
            locator = ref.locator
            if locator.page not in page_numbers:
                raise ValueError(f"source ref {ref.source_ref_id} uses unknown page")
            if locator.block_id is not None and locator.block_id not in block_ids:
                raise ValueError(f"source ref {ref.source_ref_id} uses unknown block")
            if locator.source_equation_id is not None and locator.source_equation_id not in equation_ids:
                raise ValueError(f"source ref {ref.source_ref_id} uses unknown source equation")
            if locator.asset_id is not None and locator.asset_id not in asset_ids:
                raise ValueError(f"source ref {ref.source_ref_id} uses unknown asset")
            if ref.source_type == "text_span" and locator.char_start is not None:
                block_text = blocks_by_id[locator.block_id].text
                if locator.char_end > len(block_text):
                    raise ValueError(f"source ref {ref.source_ref_id} exceeds block text")
                if block_text[locator.char_start : locator.char_end] != ref.quote:
                    raise ValueError(f"source ref {ref.source_ref_id} quote does not match block text")
            if ref.source_type == "equation":
                source_equation = equations_by_id[locator.source_equation_id]
                expected_quote = source_equation.latex or source_equation.raw_text
                if expected_quote != ref.quote:
                    raise ValueError(f"source ref {ref.source_ref_id} quote does not match equation")
            if ref.source_type == "caption":
                source_caption = assets_by_id[locator.asset_id].caption
                if source_caption != ref.quote:
                    raise ValueError(f"source ref {ref.source_ref_id} quote does not match caption")
        return self
