"""Six structured reviewers, four of which are fully deterministic."""

from __future__ import annotations

import re
from collections import Counter
from typing import Iterable, Literal

from pydantic import Field

from papercraft.models import DocumentIR, EvidenceGraph, PaperAnalysis, PosterPlan, ReviewResult
from papercraft.models.common import StrictModel
from papercraft.models.review_result import (
    CheckerSummary,
    InputRevisions,
    IssueTarget,
    RepairBatch,
    ReviewIssue,
    SuggestedPatch,
)


class ComponentRenderMetric(StrictModel):
    component_id: str
    clipped: bool = False
    overlap: bool = False
    canvas_overflow: bool = False
    chart_label_clipped: bool = False
    text_truncated: bool = False
    content_utilization_ratio: float = Field(default=1.0, ge=0, le=1)
    blank_area_ratio: float = Field(default=0.0, ge=0, le=1)
    visual_center_offset: float = Field(default=0.0, ge=0, le=1)
    allocated_area_ratio: float = Field(default=0.0, ge=0, le=1)
    formula_count: int = Field(default=0, ge=0)
    minimum_font_size: float = Field(gt=0)
    minimum_gap: float = Field(ge=0)


class NarrativeRenderMetric(StrictModel):
    role: Literal["problem", "motivation", "key_insight"]
    headline_clipped: bool = False
    body_clipped: bool = False
    headline_overflow: bool = False
    body_overflow: bool = False
    text_truncated: bool = False


class RenderMetrics(StrictModel):
    profile: Literal["screen_16_9", "print_a0_landscape"]
    render_revision: int = Field(ge=1)
    occupied_area_ratio: float = Field(ge=0, le=1)
    visual_area_ratio: float = Field(ge=0, le=1)
    reading_order_valid: bool
    density_imbalance: float = Field(ge=0, le=1)
    components: list[ComponentRenderMetric]
    narratives: list[NarrativeRenderMetric] = Field(default_factory=list)
    poster_title_overflow: bool = False
    summary_clipped_components: list[str] = Field(default_factory=list)


CHECKERS = (
    "source_consistency",
    "content_completeness",
    "evidence_sufficiency",
    "formula_accuracy",
    "global_layout",
    "local_overflow",
)


def run_deterministic_review(
    document_ir: DocumentIR,
    analysis: PaperAnalysis,
    evidence: EvidenceGraph,
    plan: PosterPlan,
    *,
    render_metrics: Iterable[RenderMetrics] = (),
    artifact_revision: int = 1,
) -> ReviewResult:
    issues: list[ReviewIssue] = []
    issue_counter = 0

    def add(
        checker: str,
        code: str,
        severity: str,
        artifact: str,
        target_id: str | None,
        message: str,
        *,
        field: str | None = None,
        detector_evidence: dict | None = None,
        patch: SuggestedPatch | None = None,
    ) -> None:
        nonlocal issue_counter
        issue_counter += 1
        issues.append(
            ReviewIssue(
                issue_id=f"issue_{issue_counter:04d}",
                checker=checker,
                code=code,
                severity=severity,
                target=IssueTarget(artifact=artifact, target_id=target_id, field=field),
                message=message,
                detector_evidence=detector_evidence or {},
                suggested_patch=patch,
                status="open",
            )
        )

    _source_review(document_ir, analysis, evidence, plan, add)
    _content_review(analysis, plan, add)
    _evidence_review(analysis, evidence, plan, add)
    _formula_review(document_ir, analysis, add)
    _layout_review(plan, list(render_metrics), add)

    summaries = []
    for checker in CHECKERS:
        checker_issues = [item for item in issues if item.checker == checker]
        summaries.append(
            CheckerSummary(
                checker=checker,
                status=(
                    "failed"
                    if any(item.severity == "error" for item in checker_issues)
                    else "passed"
                ),
                issue_count=len(checker_issues),
            )
        )
    affected = _unique(
        item.suggested_patch.target_id
        for item in issues
        if item.suggested_patch is not None
    )
    component_ids = [item.component_id for item in plan.components]
    return ReviewResult(
        schema_version="1.2.0",
        artifact_revision=artifact_revision,
        review_id=f"rev_{document_ir.paper_id.removeprefix('ppr_')}_{artifact_revision}",
        paper_id=document_ir.paper_id,
        input_revisions=InputRevisions(
            document_ir=document_ir.artifact_revision,
            paper_analysis=analysis.artifact_revision,
            evidence_graph=evidence.artifact_revision,
            poster_plan=plan.artifact_revision,
            html_render=max(
                (item.render_revision for item in render_metrics if item.profile == "screen_16_9"),
                default=None,
            ),
            pdf_render=max(
                (
                    item.render_revision
                    for item in render_metrics
                    if item.profile == "print_a0_landscape"
                ),
                default=None,
            ),
        ),
        status="failed" if any(item.severity == "error" for item in issues) else "passed",
        checker_summaries=summaries,
        issues=issues,
        repair_batch=RepairBatch(
            operations=_unique_patches(
                item.suggested_patch for item in issues if item.suggested_patch
            ),
            affected_component_ids=affected,
            must_preserve_component_ids=[
                component_id for component_id in component_ids if component_id not in affected
            ],
        ),
        metrics={
            "source_ref_coverage": _source_coverage(document_ir, analysis, evidence, plan),
            "claim_assessment_coverage": len(evidence.claim_assessments)
            / max(1, len(analysis.claims)),
            "formula_count": len(analysis.equations),
            "component_count": len(plan.components),
            "narrative_region_count": len(plan.narrative_regions),
            "source_presentation_count": len(plan.source_presentations),
        },
    )


def _source_review(document_ir, analysis, evidence, plan, add):
    valid = {item.source_ref_id for item in document_ir.source_refs}
    refs: list[tuple[str, str, str]] = []
    for collection, artifact in (
        (analysis.concepts, "paper_analysis"),
        (analysis.claims, "paper_analysis"),
        (analysis.methods, "paper_analysis"),
        (analysis.equations, "paper_analysis"),
        (analysis.experiments, "paper_analysis"),
        (evidence.evidence, "evidence_graph"),
        (plan.components, "poster_plan"),
        (plan.narrative_regions, "poster_plan"),
        (plan.source_presentations, "poster_plan"),
    ):
        for item in collection:
            target_id = _object_id(item)
            item_refs = getattr(item, "source_refs", None)
            if item_refs is None and getattr(item, "source_ref_id", None):
                item_refs = [item.source_ref_id]
            refs.extend((artifact, target_id, ref) for ref in (item_refs or []))
            for child in getattr(item, "steps", []):
                refs.extend((artifact, target_id, ref) for ref in child.source_refs)
            for child in getattr(item, "results", []):
                refs.extend((artifact, child.result_id, ref) for ref in child.source_refs)
    for artifact, target_id, ref in refs:
        if ref not in valid:
            add(
                "source_consistency",
                "UNRESOLVABLE_SOURCE_REF",
                "error",
                artifact,
                target_id,
                f"Source reference {ref} does not exist in DocumentIR.",
                detector_evidence={"source_ref_id": ref},
            )

    caption_boxes = {block.text: block.bbox for block in document_ir.blocks if block.block_type == "caption"}
    for asset in document_ir.assets:
        if asset.asset_type != "figure":
            continue
        caption_box = caption_boxes.get(asset.caption)
        if caption_box is not None and asset.bbox.y0 >= caption_box.y0 - 24:
            add(
                "source_consistency",
                "SOURCE_PREVIEW_INCOMPLETE",
                "error",
                "document_ir",
                asset.asset_id,
                "Figure crop does not include a meaningful visual region above its caption.",
                field="bbox",
                detector_evidence={
                    "asset_y0": asset.bbox.y0,
                    "caption_y0": caption_box.y0,
                },
            )

    quote_by_id = {item.source_ref_id: item.quote for item in document_ir.source_refs}
    for experiment in analysis.experiments:
        for result in experiment.results:
            source_text = " ".join(quote_by_id.get(ref, "") for ref in result.source_refs)
            missing_numbers = [
                value
                for value in _numbers(result.value)
                if not _number_in_text(value, source_text)
            ]
            if missing_numbers:
                image_backed = any(
                    ref.startswith(("src_ast_table_", "src_ast_figure_"))
                    for ref in result.source_refs
                )
                add(
                    "source_consistency",
                    "NUMERIC_MISMATCH",
                    "warning" if image_backed else "error",
                    "paper_analysis",
                    result.result_id,
                    (
                        "Numbers are grounded in a cited table image and require visual/OCR verification."
                        if image_backed
                        else "One or more reported result numbers do not occur in the cited source."
                    ),
                    detector_evidence={"missing_numbers": missing_numbers},
                )
    for warning in analysis.analysis_warnings:
        if "Table" in warning and ("not" in warning or "conflict" in warning):
            add(
                "source_consistency",
                "NUMERIC_MISMATCH",
                "warning",
                "paper_analysis",
                None,
                warning,
            )


def _content_review(analysis, plan, add):
    concept_types = {item.concept_type for item in analysis.concepts}
    for required in ("problem", "motivation", "key_insight", "conclusion"):
        if required not in concept_types:
            add(
                "content_completeness",
                "MISSING_REQUIRED_CONTENT",
                "error",
                "paper_analysis",
                None,
                f"Paper analysis is missing a {required} concept.",
                field="concepts",
            )
    if analysis.schema_version == "1.2.0" and analysis.narrative_frame is None:
        add(
            "content_completeness",
            "MISSING_REQUIRED_CONTENT",
            "error",
            "paper_analysis",
            None,
            "PosterPlan 1.2 requires a structured narrative frame.",
            field="narrative_frame",
        )
    if plan.schema_version == "1.2.0" and len(plan.narrative_regions) != 3:
        add(
            "content_completeness",
            "MISSING_REQUIRED_CONTENT",
            "error",
            "poster_plan",
            None,
            "PosterPlan 1.2 requires three formal narrative regions.",
            field="narrative_regions",
        )
    component_types = {item.component_type for item in plan.components}
    required_components = {"method_flow", "result_chart"}
    if plan.evidence_visibility == "visible_panel":
        required_components.add("claim_evidence_chain")
    if plan.narrative_mode in {"mechanism", "balanced"} and analysis.equations:
        required_components.add("equation_explorer")
    if plan.narrative_mode == "qualitative":
        required_components.add("visual_gallery")
    for required in sorted(required_components):
        if required not in component_types:
            add(
                "content_completeness",
                "MISSING_REQUIRED_CONTENT",
                "error",
                "poster_plan",
                None,
                f"Poster is missing the required {required} component family.",
                field="components",
            )
    method_components = [item for item in plan.components if item.component_type == "method_flow"]
    for component in method_components:
        if not component.asset_refs:
            add(
                "content_completeness",
                "SOURCE_PREVIEW_MISSING",
                "error",
                "poster_plan",
                component.component_id,
                "The primary method component must reference a method overview figure for Screen and Inspector use.",
                field="asset_refs",
            )
    normalized = [re.sub(r"\W+", " ", item.statement.lower()).strip() for item in analysis.claims]
    duplicates = [text for text, count in Counter(normalized).items() if count > 1]
    for duplicate in duplicates:
        add(
            "content_completeness",
            "DUPLICATE_CONTENT",
            "warning",
            "paper_analysis",
            None,
            "Two claims repeat the same normalized statement.",
            detector_evidence={"normalized_statement": duplicate},
        )


def _evidence_review(analysis, evidence, plan, add):
    assessments = {item.claim_id: item for item in evidence.claim_assessments}
    expected_dimensions = {
        "directness",
        "scope_match",
        "baseline_adequacy",
        "ablation_support",
        "robustness",
        "statistical_support",
    }
    component_for_claim = {
        claim_id: component.component_id
        for component in plan.components
        for claim_id in component.claim_refs
    }
    for claim in analysis.claims:
        assessment = assessments.get(claim.claim_id)
        if assessment is None:
            add(
                "evidence_sufficiency",
                "EVIDENCE_SCOPE_MISMATCH",
                "error",
                "evidence_graph",
                claim.claim_id,
                "Claim has no evidence assessment.",
            )
            continue
        actual_dimensions = {item.dimension for item in assessment.sufficiency_checks}
        if actual_dimensions != expected_dimensions:
            add(
                "evidence_sufficiency",
                "MISSING_ABLATION_SUPPORT",
                "error",
                "evidence_graph",
                claim.claim_id,
                "Claim assessment does not cover all six sufficiency dimensions.",
                detector_evidence={"missing": sorted(expected_dimensions - actual_dimensions)},
            )
        if (
            assessment.status == "insufficient_evidence"
            and claim.claim_id in component_for_claim
            and not getattr(
                next(
                    (item for item in plan.components if item.component_id == component_for_claim[claim.claim_id]),
                    None,
                ),
                "show_assessment_status",
                False,
            )
        ):
            component_id = component_for_claim[claim.claim_id]
            add(
                "evidence_sufficiency",
                "UNSUPPORTED_CLAIM_LANGUAGE",
                "error",
                "poster_plan",
                component_id,
                "An insufficient-evidence claim is included without an explicit downgrade.",
                patch=SuggestedPatch(
                    patch_id=f"patch_qualify_{claim.claim_id.removeprefix('clm_')}",
                    operation="qualify_claim",
                    target_id=component_id,
                    parameters={"claim_id": claim.claim_id},
                    expected_revision=plan.artifact_revision,
                ),
            )


def _formula_review(document_ir, analysis, add):
    source_equations = {item.source_equation_id: item for item in document_ir.equations}
    for equation in analysis.equations:
        source = source_equations.get(equation.source_equation_id)
        if source is None:
            add(
                "formula_accuracy",
                "FORMULA_SOURCE_MISMATCH",
                "error",
                "paper_analysis",
                equation.equation_id,
                "Formula references a missing DocumentIR equation.",
            )
            continue
        source_label = _normalized_equation_label(source.label)
        analysis_label = _normalized_equation_label(equation.label)
        if source_label and analysis_label != source_label:
            add(
                "formula_accuracy",
                "FORMULA_SYMBOL_MISMATCH",
                "error",
                "paper_analysis",
                equation.equation_id,
                "Formula label differs from its source equation.",
                detector_evidence={"source_label": source.label, "analysis_label": equation.label},
            )
        if not equation.variables:
            add(
                "formula_accuracy",
                "FORMULA_VARIABLE_UNDEFINED",
                "error",
                "paper_analysis",
                equation.equation_id,
                "Formula has no variable definitions.",
            )
        reverse_method_refs = {
            method.method_id
            for method in analysis.methods
            if equation.equation_id in method.equation_refs
        }
        # Definitions and constraints can explain the paper's conceptual frame
        # without belonging to an implementation step. Objectives and update
        # rules, however, must be connected to a method in at least one of the
        # model's two reciprocal reference fields.
        if (
            equation.semantic_role in {"objective", "update_rule"}
            and not equation.method_refs
            and not reverse_method_refs
        ):
            add(
                "formula_accuracy",
                "FORMULA_METHOD_LINK_MISSING",
                "error",
                "paper_analysis",
                equation.equation_id,
                "Formula is not linked to a method.",
            )
        if not equation.experiment_refs:
            add(
                "formula_accuracy",
                "FORMULA_EXPERIMENT_LINK_MISSING",
                "warning",
                "paper_analysis",
                equation.equation_id,
                "Formula has no explicit experimental link.",
            )


def _normalized_equation_label(label: str | None) -> str | None:
    if label is None:
        return None
    normalized = label.strip()
    while len(normalized) >= 2 and normalized[0] == "(" and normalized[-1] == ")":
        normalized = normalized[1:-1].strip()
    return normalized or None


def _layout_review(plan, render_metrics, add):
    metrics_by_profile = {item.profile: item for item in render_metrics}
    narrative_patch_target = next(
        (item.component_id for item in plan.components if item.component_type == "method_flow"),
        plan.components[0].component_id,
    )
    for metrics in render_metrics:
        artifact = "html_render" if metrics.profile == "screen_16_9" else "pdf_render"
        if metrics.poster_title_overflow:
            add(
                "local_overflow",
                "POSTER_TITLE_OVERFLOW",
                "error",
                artifact,
                "poster:title",
                "The poster title exceeds its rendered width.",
                patch=SuggestedPatch(
                    patch_id=f"patch_title_{metrics.profile}",
                    operation="shorten_title",
                    target_id=narrative_patch_target,
                    parameters={"maximum_characters": 72, "profile": metrics.profile},
                    expected_revision=plan.artifact_revision,
                ),
            )
        for narrative in metrics.narratives:
            checks = (
                (narrative.headline_clipped, "NARRATIVE_HEADLINE_CLIPPED", "Narrative headline is clipped."),
                (narrative.body_clipped, "NARRATIVE_BODY_CLIPPED", "Narrative body is clipped."),
                (narrative.headline_overflow, "NARRATIVE_HEADLINE_OVERFLOW", "Narrative headline overflows its region."),
                (narrative.body_overflow, "NARRATIVE_BODY_OVERFLOW", "Narrative body overflows its region."),
                (narrative.text_truncated, "NARRATIVE_TEXT_TRUNCATED", "Narrative text is line-clamped or visibly abbreviated."),
            )
            for condition, code, message in checks:
                if not condition:
                    continue
                add(
                    "local_overflow",
                    code,
                    "error",
                    artifact,
                    f"narrative:{narrative.role}",
                    message,
                    patch=SuggestedPatch(
                        patch_id=f"patch_narrative_{narrative.role}_{metrics.profile}_{code.lower()}",
                        operation="shorten_narrative",
                        target_id=narrative_patch_target,
                        parameters={
                            "role": narrative.role,
                            "maximum_characters": 240,
                            "profile": metrics.profile,
                        },
                        expected_revision=plan.artifact_revision,
                    ),
                )
        for component_id in metrics.summary_clipped_components:
            add(
                "local_overflow",
                "COMPONENT_SUMMARY_CLIPPED",
                "error",
                artifact,
                component_id,
                "Component summary is clipped.",
                patch=SuggestedPatch(
                    patch_id=f"patch_summary_{component_id}_{metrics.profile}",
                    operation="shorten_summary",
                    target_id=component_id,
                    parameters={"maximum_characters": 170, "profile": metrics.profile},
                    expected_revision=plan.artifact_revision,
                ),
            )
    for profile_name, profile in (
        ("screen_16_9", plan.layout_profiles.screen_16_9),
        ("print_a0_landscape", plan.layout_profiles.print_a0_landscape),
    ):
        metrics = metrics_by_profile.get(profile_name)
        if metrics is None:
            continue
        artifact = "html_render" if profile_name == "screen_16_9" else "pdf_render"
        target = profile.occupancy.target_interval
        if not target.minimum - 0.002 <= metrics.occupied_area_ratio <= target.maximum + 0.002:
            add(
                "global_layout",
                "OCCUPANCY_OUT_OF_RANGE",
                "error",
                "poster_plan",
                None,
                f"{profile_name} occupancy is outside its dynamic target interval.",
                detector_evidence={
                    "actual": metrics.occupied_area_ratio,
                    "minimum": target.minimum,
                    "maximum": target.maximum,
                },
            )
        visual = profile.visual_area_ratio
        if not visual.minimum - 0.002 <= metrics.visual_area_ratio <= visual.maximum + 0.002:
            add(
                "global_layout",
                "VISUAL_RATIO_OUT_OF_RANGE",
                "error",
                "poster_plan",
                None,
                f"{profile_name} visual/text ratio is outside its configured bounds.",
                detector_evidence={"actual": metrics.visual_area_ratio},
            )
        if not metrics.reading_order_valid:
            add(
                "global_layout",
                "READING_ORDER_BROKEN",
                "error",
                "poster_plan",
                None,
                f"{profile_name} visual order does not match reading_path.",
            )
        if metrics.density_imbalance > 0.35:
            add(
                "global_layout",
                "DENSITY_IMBALANCE",
                "warning",
                "poster_plan",
                None,
                f"{profile_name} has a large density imbalance between components.",
                detector_evidence={"imbalance": metrics.density_imbalance},
            )
        min_font = (
            profile.typography.body_min_px
            if profile_name == "screen_16_9"
            else profile.typography.body_min_pt
        )
        min_gap = (
            profile.minimum_component_gap_px
            if profile_name == "screen_16_9"
            else profile.minimum_component_gap_mm
        )
        component_types = {item.component_id: item.component_type for item in plan.components}
        for component in metrics.components:
            patch = SuggestedPatch(
                patch_id=f"patch_resize_{component.component_id.removeprefix('cmp_')}_{profile_name}",
                operation="resize",
                target_id=component.component_id,
                parameters={"profile": profile_name},
                expected_revision=plan.artifact_revision,
            )
            if component.minimum_font_size < min_font:
                add(
                    "local_overflow",
                    "FONT_BELOW_MINIMUM",
                    "error",
                    "html_render" if profile_name == "screen_16_9" else "pdf_render",
                    component.component_id,
                    "Rendered body text is below the configured minimum.",
                    detector_evidence={"actual": component.minimum_font_size, "minimum": min_font},
                    patch=patch,
                )
            if component.minimum_gap + 0.001 < min_gap:
                add(
                    "local_overflow",
                    "GAP_BELOW_MINIMUM",
                    "error",
                    "html_render" if profile_name == "screen_16_9" else "pdf_render",
                    component.component_id,
                    "Rendered component gap is below the configured minimum.",
                    detector_evidence={"actual": component.minimum_gap, "minimum": min_gap},
                    patch=SuggestedPatch(
                        patch_id=f"patch_gap_{component.component_id.removeprefix('cmp_')}_{profile_name}",
                        operation="increase_gap",
                        target_id=component.component_id,
                        parameters={"profile": profile_name, "minimum": min_gap},
                        expected_revision=plan.artifact_revision,
                    ),
                )
            if component.content_utilization_ratio < 0.34:
                add(
                    "global_layout",
                    "LOW_COMPONENT_UTILIZATION",
                    "warning",
                    artifact,
                    component.component_id,
                    "The component uses too little of its allocated area.",
                    detector_evidence={
                        "utilization": component.content_utilization_ratio,
                        "blank_area": component.blank_area_ratio,
                    },
                )
            if component.blank_area_ratio > 0.58:
                add(
                    "global_layout",
                    "LARGE_BLANK_REGION",
                    "warning",
                    artifact,
                    component.component_id,
                    "A large internal blank region remains inside the component.",
                    detector_evidence={"blank_area": component.blank_area_ratio},
                )
            if component.visual_center_offset > 0.42:
                add(
                    "global_layout",
                    "VISUAL_CENTER_IMBALANCE",
                    "warning",
                    artifact,
                    component.component_id,
                    "Visible content is concentrated too far from the component center.",
                    detector_evidence={"center_offset": component.visual_center_offset},
                )
            if (
                component_types.get(component.component_id) == "equation_explorer"
                and component.allocated_area_ratio >= 0.08
                and component.formula_count < (3 if component.allocated_area_ratio >= 0.14 else 2)
            ):
                add(
                    "global_layout",
                    "FORMULA_AREA_MISMATCH",
                    "warning",
                    artifact,
                    component.component_id,
                    "The equation panel area is not supported by enough visible formulas.",
                    detector_evidence={
                        "allocated_area": component.allocated_area_ratio,
                        "formula_count": component.formula_count,
                    },
                )
            for condition, code, message in (
                (component.clipped, "TEXT_CLIPPED", "Text is clipped."),
                (component.overlap, "ELEMENT_OVERLAP", "Elements overlap."),
                (component.canvas_overflow, "CANVAS_OVERFLOW", "Component leaves the canvas."),
                (component.chart_label_clipped, "CHART_LABEL_CLIPPED", "Chart label is clipped."),
                (component.text_truncated, "TEXT_TRUNCATED", "Text is line-clamped or visibly abbreviated."),
            ):
                if condition:
                    add(
                        "local_overflow",
                        code,
                        "error",
                        "html_render" if profile_name == "screen_16_9" else "pdf_render",
                        component.component_id,
                        f"{profile_name}: {message}",
                        patch=patch,
                    )


def _source_coverage(document_ir, analysis, evidence, plan):
    objects = (
        list(analysis.concepts)
        + list(analysis.claims)
        + list(analysis.methods)
        + list(analysis.equations)
        + list(analysis.experiments)
        + list(evidence.evidence)
        + list(plan.components)
        + list(plan.narrative_regions)
        + list(plan.source_presentations)
    )
    return sum(
        bool(getattr(item, "source_refs", None) or getattr(item, "source_ref_id", None))
        for item in objects
    ) / max(1, len(objects))


def _object_id(item):
    for name in (
        "concept_id",
        "claim_id",
        "method_id",
        "equation_id",
        "experiment_id",
        "evidence_id",
        "component_id",
    ):
        value = getattr(item, name, None)
        if value:
            return value
    return "unknown"


def _numbers(text: str) -> list[str]:
    return re.findall(r"(?<![A-Za-z])\d+(?:\.\d+)?", text.replace(",", ""))


def _number_in_text(value: str, text: str) -> bool:
    normalized = text.replace(",", "")
    if re.search(rf"(?<!\d){re.escape(value)}(?!\d)", normalized) is not None:
        return True
    target = float(value)
    source_values = [float(item) for item in _numbers(normalized)]
    return any(
        abs(abs(left - right) - target) < 1e-6
        for index, left in enumerate(source_values)
        for right in source_values[index + 1 :]
    )


def _unique(values):
    return list(dict.fromkeys(values))


def _unique_patches(values):
    unique = {}
    for patch in values:
        key = (patch.operation, patch.target_id, str(sorted(patch.parameters.items())))
        unique.setdefault(key, patch)
    return list(unique.values())
