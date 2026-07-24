"""Semantic poster components plus independent Screen and Print layouts."""

from __future__ import annotations

from typing import Annotated, Literal, Union

from pydantic import Field, PositiveFloat, PositiveInt, model_validator

from papercraft.models.common import (
    ClaimId,
    ComponentId,
    EquationId,
    EvidenceId,
    ExperimentId,
    MethodId,
    PaperId,
    Ratio,
    ResultId,
    SchemaVersion,
    SourceRefId,
    StrictModel,
    ensure_unique,
)
from papercraft.models.document_ir import BoundingBox


NarrativeMode = Literal["mechanism", "benchmark", "ablation", "qualitative", "balanced"]
EvidenceVisibility = Literal["visible_panel", "inspector", "internal_only"]


class Interaction(StrictModel):
    event: Literal["click"]
    action: Literal[
        "expand_details",
        "show_source",
        "toggle_original_reconstruction",
        "collapse_secondary",
    ]


class FlowStep(StrictModel):
    label: str = Field(min_length=1)
    description: str = Field(min_length=1)
    source_refs: list[SourceRefId] = Field(min_length=1)


class TextBudget(StrictModel):
    headline_max_chars: PositiveInt
    body_max_chars: PositiveInt
    summary_max_chars: PositiveInt
    headline_max_lines: PositiveInt
    body_max_lines: PositiveInt
    summary_max_lines: PositiveInt


class NarrativeRegion(StrictModel):
    role: Literal["problem", "motivation", "key_insight"]
    eyebrow: str = Field(min_length=1)
    headline: str = Field(min_length=1)
    body: str = Field(min_length=1)
    source_refs: list[SourceRefId] = Field(min_length=1)
    presentation_ref: str | None = None
    text_budget: TextBudget | None = None


class SourcePresentation(StrictModel):
    presentation_id: str = Field(pattern=r"^prs_[a-z0-9_]+$")
    source_ref_id: SourceRefId
    role: Literal[
        "teaser",
        "method_overview",
        "mechanism",
        "qualitative_result",
        "benchmark",
        "formula",
        "source_only",
    ]
    display_kind: Literal[
        "text_excerpt",
        "pdf_crop",
        "reconstructed_equation",
        "reconstructed_chart",
        "source_figure",
    ]
    title: str = Field(min_length=1)
    page: PositiveInt
    crop_bbox: BoundingBox | None = None
    asset_ref: str | None = None
    image_path: str | None = None
    equation_ref: EquationId | None = None
    result_refs: list[ResultId] = Field(default_factory=list)
    fallback_to_crop: bool = True


class EquationGroup(StrictModel):
    group_id: str = Field(pattern=r"^eqg_[a-z0-9_]+$")
    title: str = Field(min_length=1)
    explanation: str = Field(min_length=1)
    equation_refs: list[EquationId] = Field(min_length=1)


class MethodInspectorPanel(StrictModel):
    panel_id: str = Field(pattern=r"^mip_[a-z0-9_]+$")
    method_ref: MethodId
    title: str = Field(min_length=1)
    why_needed: str = Field(min_length=1)
    inputs: list[str]
    outputs: list[str]
    equation_refs: list[EquationId] = Field(default_factory=list)
    experiment_refs: list[ExperimentId] = Field(default_factory=list)
    source_refs: list[SourceRefId] = Field(min_length=1)
    presentation_refs: list[str] = Field(default_factory=list)


class ComponentBase(StrictModel):
    component_id: ComponentId
    title: str = Field(min_length=1)
    summary: str = Field(min_length=1)
    content_refs: list[str] = Field(min_length=1)
    source_refs: list[SourceRefId] = Field(min_length=1)
    claim_refs: list[ClaimId] = Field(default_factory=list)
    evidence_refs: list[EvidenceId] = Field(default_factory=list)
    asset_refs: list[str] = Field(default_factory=list)
    interactions: list[Interaction] = Field(default_factory=list)
    details: list[str] = Field(default_factory=list)


class MethodFlowComponent(ComponentBase):
    component_type: Literal["method_flow"]
    method_refs: list[MethodId] = Field(min_length=1)
    steps: list[FlowStep] = Field(min_length=2)
    inspector_panels: list[MethodInspectorPanel] = Field(default_factory=list)


class EquationExplorerComponent(ComponentBase):
    component_type: Literal["equation_explorer"]
    equation_refs: list[EquationId] = Field(min_length=1)
    show_variable_table: bool = True
    show_computation_steps: bool = True
    equation_groups: list[EquationGroup] = Field(default_factory=list)


class ClaimEvidenceChainComponent(ComponentBase):
    component_type: Literal["claim_evidence_chain"]
    claim_refs: list[ClaimId] = Field(min_length=1)
    evidence_refs: list[EvidenceId] = Field(min_length=1)
    experiment_refs: list[ExperimentId] = Field(default_factory=list)
    show_assessment_status: bool = True


class ChartDatum(StrictModel):
    label: str = Field(min_length=1)
    value: float
    display_value: str = Field(min_length=1)
    series: str = Field(min_length=1)


class ResultChartComponent(ComponentBase):
    component_type: Literal["result_chart"]
    experiment_refs: list[ExperimentId] = Field(min_length=1)
    result_refs: list[ResultId] = Field(min_length=1)
    chart_type: Literal["bar", "line", "comparison_table"]
    chart_data: list[ChartDatum] = Field(default_factory=list)


class VisualGalleryComponent(ComponentBase):
    component_type: Literal["visual_gallery"]
    presentation_refs: list[str] = Field(min_length=1)
    caption_mode: Literal["compact", "full"] = "compact"


PosterComponent = Annotated[
    Union[
        MethodFlowComponent,
        EquationExplorerComponent,
        ClaimEvidenceChainComponent,
        ResultChartComponent,
        VisualGalleryComponent,
    ],
    Field(discriminator="component_type"),
]


class ThemeTokens(StrictModel):
    family: Literal["technical", "clinical", "editorial"]
    background: str = Field(pattern=r"^#[0-9A-Fa-f]{6}$")
    surface: str = Field(pattern=r"^#[0-9A-Fa-f]{6}$")
    foreground: str = Field(pattern=r"^#[0-9A-Fa-f]{6}$")
    muted: str = Field(pattern=r"^#[0-9A-Fa-f]{6}$")
    accent: str = Field(pattern=r"^#[0-9A-Fa-f]{6}$")
    accent_secondary: str = Field(pattern=r"^#[0-9A-Fa-f]{6}$")
    success: str = Field(pattern=r"^#[0-9A-Fa-f]{6}$")
    warning: str = Field(pattern=r"^#[0-9A-Fa-f]{6}$")
    danger: str = Field(pattern=r"^#[0-9A-Fa-f]{6}$")


class RatioRange(StrictModel):
    minimum: Ratio
    maximum: Ratio

    @model_validator(mode="after")
    def ordered(self) -> "RatioRange":
        if self.maximum < self.minimum:
            raise ValueError("range maximum must not be below minimum")
        return self


class OccupancyPolicy(StrictModel):
    calculation_method: Literal["intrinsic_demand"]
    raw_demand_ratio: Ratio
    tolerance: float = Field(gt=0.0, le=0.1)
    absolute_bounds: RatioRange
    target_interval: RatioRange

    @model_validator(mode="after")
    def target_inside_bounds(self) -> "OccupancyPolicy":
        if self.target_interval.minimum < self.absolute_bounds.minimum:
            raise ValueError("occupancy target minimum is outside absolute bounds")
        if self.target_interval.maximum > self.absolute_bounds.maximum:
            raise ValueError("occupancy target maximum is outside absolute bounds")
        return self


class ComponentPlacement(StrictModel):
    component_id: ComponentId
    order: PositiveInt
    column_start: PositiveInt
    column_span: PositiveInt
    row_start: PositiveInt
    row_span: PositiveInt
    minimum_height: PositiveFloat
    preferred_height: PositiveFloat

    @model_validator(mode="after")
    def height_order(self) -> "ComponentPlacement":
        if self.preferred_height < self.minimum_height:
            raise ValueError("preferred_height must not be below minimum_height")
        return self


class ScreenCanvas(StrictModel):
    width_px: Literal[1920]
    height_px: Literal[1080]


class ScreenTypography(StrictModel):
    title_min_px: int = Field(ge=32)
    body_min_px: int = Field(ge=18)
    caption_min_px: int = Field(ge=14)


class ScreenLayoutProfile(StrictModel):
    profile: Literal["screen_16_9"]
    canvas: ScreenCanvas
    occupancy: OccupancyPolicy
    typography: ScreenTypography
    visual_area_ratio: RatioRange
    minimum_component_gap_px: float = Field(ge=16.0)
    component_layouts: list[ComponentPlacement] = Field(min_length=1)

    @model_validator(mode="after")
    def architectural_limits(self) -> "ScreenLayoutProfile":
        bounds = self.occupancy.absolute_bounds
        if bounds.minimum < 0.72 or bounds.maximum > 0.90:
            raise ValueError("screen occupancy bounds must stay within 0.72..0.90")
        ratio = self.visual_area_ratio
        if ratio.minimum < 0.35 or ratio.maximum > 0.80:
            raise ValueError("screen visual ratio must stay within 0.35..0.80")
        ensure_unique((item.component_id for item in self.component_layouts), "screen component placement")
        return self


class PrintCanvas(StrictModel):
    width_mm: Literal[1189]
    height_mm: Literal[841]
    orientation: Literal["landscape"]


class PrintTypography(StrictModel):
    title_min_pt: int = Field(ge=48)
    body_min_pt: int = Field(ge=24)
    caption_min_pt: int = Field(ge=18)


class PrintLayoutProfile(StrictModel):
    profile: Literal["print_a0_landscape"]
    canvas: PrintCanvas
    occupancy: OccupancyPolicy
    typography: PrintTypography
    visual_area_ratio: RatioRange
    minimum_component_gap_mm: float = Field(ge=8.0)
    component_layouts: list[ComponentPlacement] = Field(min_length=1)

    @model_validator(mode="after")
    def architectural_limits(self) -> "PrintLayoutProfile":
        bounds = self.occupancy.absolute_bounds
        if bounds.minimum < 0.78 or bounds.maximum > 0.94:
            raise ValueError("print occupancy bounds must stay within 0.78..0.94")
        ratio = self.visual_area_ratio
        if ratio.minimum < 0.35 or ratio.maximum > 0.90:
            raise ValueError("print visual ratio must stay within 0.35..0.90")
        ensure_unique((item.component_id for item in self.component_layouts), "print component placement")
        return self


class LayoutProfiles(StrictModel):
    screen_16_9: ScreenLayoutProfile
    print_a0_landscape: PrintLayoutProfile


class PosterPlan(StrictModel):
    schema_version: SchemaVersion
    artifact_revision: PositiveInt
    paper_id: PaperId
    analysis_revision: PositiveInt
    evidence_revision: PositiveInt
    narrative_mode: NarrativeMode = "balanced"
    evidence_visibility: EvidenceVisibility = "visible_panel"
    theme: ThemeTokens | None = None
    narrative_regions: list[NarrativeRegion] = Field(default_factory=list)
    source_presentations: list[SourcePresentation] = Field(default_factory=list)
    reading_path: list[ComponentId] = Field(min_length=1)
    components: list[PosterComponent] = Field(min_length=1)
    layout_profiles: LayoutProfiles

    @model_validator(mode="after")
    def component_integrity(self) -> "PosterPlan":
        component_ids = [item.component_id for item in self.components]
        ensure_unique(component_ids, "poster component ID")
        ensure_unique(
            (item.presentation_id for item in self.source_presentations),
            "source presentation ID",
        )
        if self.schema_version == "1.2.0":
            roles = {item.role for item in self.narrative_regions}
            if roles != {"problem", "motivation", "key_insight"}:
                raise ValueError("poster plan 1.2 requires Problem, Motivation, and Key Insight regions")
        ensure_unique(self.reading_path, "reading path component ID")
        expected = set(component_ids)
        if set(self.reading_path) != expected:
            raise ValueError("reading_path must contain every component exactly once")
        screen = {item.component_id for item in self.layout_profiles.screen_16_9.component_layouts}
        printable = {
            item.component_id for item in self.layout_profiles.print_a0_landscape.component_layouts
        }
        if screen != expected:
            raise ValueError("screen layout must place every component exactly once")
        if printable != expected:
            raise ValueError("print layout must place every component exactly once")
        for label, placements in (
            ("screen", self.layout_profiles.screen_16_9.component_layouts),
            ("print", self.layout_profiles.print_a0_landscape.component_layouts),
        ):
            for item in placements:
                if item.column_start + item.column_span - 1 > 12:
                    raise ValueError(f"{label} component {item.component_id} exceeds 12 columns")
                if item.row_start + item.row_span - 1 > 10:
                    raise ValueError(f"{label} component {item.component_id} exceeds 10 rows")
            for index, left in enumerate(placements):
                for right in placements[index + 1 :]:
                    if _placements_overlap(left, right):
                        raise ValueError(
                            f"{label} components overlap: {left.component_id}, {right.component_id}"
                        )
        return self


def _placements_overlap(left: ComponentPlacement, right: ComponentPlacement) -> bool:
    left_column_end = left.column_start + left.column_span
    right_column_end = right.column_start + right.column_span
    left_row_end = left.row_start + left.row_span
    right_row_end = right.row_start + right.row_span
    horizontal = left.column_start < right_column_end and right.column_start < left_column_end
    vertical = left.row_start < right_row_end and right.row_start < left_row_end
    return horizontal and vertical
