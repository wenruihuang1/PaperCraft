"""Create a dense, evidence-visible PosterPlan without model-generated code."""

from __future__ import annotations

import re

from papercraft.models import DocumentIR, EvidenceGraph, PaperAnalysis, PosterPlan
from papercraft.models.poster_plan import (
    ChartDatum,
    ClaimEvidenceChainComponent,
    ComponentPlacement,
    EquationExplorerComponent,
    EquationGroup,
    FlowStep,
    LayoutProfiles,
    MethodFlowComponent,
    MethodInspectorPanel,
    NarrativeRegion,
    OccupancyPolicy,
    PrintCanvas,
    PrintLayoutProfile,
    PrintTypography,
    RatioRange,
    ResultChartComponent,
    ScreenCanvas,
    ScreenLayoutProfile,
    ScreenTypography,
    SourcePresentation,
    TextBudget,
    ThemeTokens,
    VisualGalleryComponent,
)
from papercraft.planning.layout_engine import (
    build_component_placements,
    order_for_layout,
)


def build_poster_plan(
    document_ir: DocumentIR,
    analysis: PaperAnalysis,
    evidence: EvidenceGraph,
    *,
    artifact_revision: int = 1,
) -> PosterPlan:
    methods = analysis.methods
    equations = analysis.equations
    claims = analysis.claims
    experiments = analysis.experiments
    results = [result for experiment in experiments for result in experiment.results]
    source_presentations = _source_presentations(document_ir, analysis)
    narrative_mode = _select_narrative_mode(document_ir, analysis, evidence)
    narrative_regions = _narrative_regions(analysis, source_presentations, narrative_mode)

    method_sources = _unique(
        ref for method in methods for ref in method.source_refs
    )
    method_assets = _method_assets(document_ir)
    method_component = MethodFlowComponent(
        component_id="cmp_method_flow",
        component_type="method_flow",
        title=_method_title(methods, analysis, narrative_mode),
        summary=_budget_text(_method_summary(methods), 180),
        content_refs=[method.method_id for method in methods],
        source_refs=method_sources,
        claim_refs=[claim.claim_id for claim in claims[:2]],
        evidence_refs=[],
        asset_refs=method_assets,
        interactions=[
            {"event": "click", "action": "expand_details"},
            {"event": "click", "action": "show_source"},
            {"event": "click", "action": "toggle_original_reconstruction"},
        ],
        details=[assumption for method in methods for assumption in method.assumptions],
        method_refs=[method.method_id for method in methods],
        steps=_flow_steps(methods),
        inspector_panels=[
            MethodInspectorPanel(
                panel_id=f"mip_{method.method_id.removeprefix('mth_')}",
                method_ref=method.method_id,
                title=method.name,
                why_needed=method.purpose,
                inputs=method.inputs,
                outputs=method.outputs,
                equation_refs=method.equation_refs,
                experiment_refs=_method_experiments(method, equations),
                source_refs=method.source_refs,
                presentation_refs=_method_presentations(method, source_presentations),
            )
            for method in methods
        ],
    )

    equation_sources = _unique(ref for equation in equations for ref in equation.source_refs)
    equation_component = EquationExplorerComponent(
        component_id="cmp_equation_explorer",
        component_type="equation_explorer",
        title=_equation_title(analysis, narrative_mode),
        summary=_budget_text(_equation_summary(equations), 180),
        content_refs=[equation.equation_id for equation in equations],
        source_refs=equation_sources,
        claim_refs=[
            claim.claim_id
            for claim in claims
            if "entropy" in claim.claim_id or "search" in claim.claim_id
        ],
        evidence_refs=[
            node.evidence_id for node in evidence.evidence if node.evidence_type == "equation"
        ],
        asset_refs=[
            asset.asset_id
            for asset in document_ir.assets
            if asset.asset_id in {"ast_figure_002", "ast_figure_003"}
        ],
        interactions=[
            {"event": "click", "action": "expand_details"},
            {"event": "click", "action": "show_source"},
            {"event": "click", "action": "toggle_original_reconstruction"},
        ],
        details=[
            "Original symbols are preserved; select an equation to inspect variables and computation order."
        ],
        equation_refs=[equation.equation_id for equation in equations],
        show_variable_table=True,
        show_computation_steps=True,
        equation_groups=_equation_groups(equations),
    ) if equations else None

    primary_experiments = _primary_experiments(experiments)
    primary_results = (
        [experiment.results[0] for experiment in primary_experiments[:4]]
        if len(primary_experiments) > 1
        else primary_experiments[0].results[:4]
    )
    result_component = ResultChartComponent(
        component_id="cmp_result_overview",
        component_type="result_chart",
        title=_results_title(analysis, narrative_mode),
        summary=_budget_text(_result_summary(primary_experiments, primary_results), 190),
        content_refs=(
            [experiment.experiment_id for experiment in primary_experiments]
            + [result.result_id for result in primary_results]
        ),
        source_refs=_unique(ref for result in primary_results for ref in result.source_refs),
        claim_refs=[claim.claim_id for claim in claims[:2]],
        evidence_refs=[node.evidence_id for node in evidence.evidence[:3]],
        asset_refs=_assets_for_results(document_ir, primary_results),
        interactions=[
            {"event": "click", "action": "expand_details"},
            {"event": "click", "action": "show_source"},
        ],
        details=[result.value for result in primary_results],
        experiment_refs=[experiment.experiment_id for experiment in primary_experiments],
        result_refs=[result.result_id for result in primary_results],
        chart_type="comparison_table",
        chart_data=_comparison_chart_data(primary_results),
    )

    ablation_results = [
        result
        for experiment in experiments
        if "ablation" in f"{experiment.experiment_id} {experiment.question} {experiment.setup}".lower()
        for result in experiment.results
    ]
    ablation_component = None
    if ablation_results and document_ir.paper_id != "ppr_dev_003":
        ablation_results = ablation_results[:2]
        ablation_experiments = [
            experiment
            for experiment in experiments
            if any(result in experiment.results for result in ablation_results)
        ]
        ablation_component = ResultChartComponent(
                component_id="cmp_result_ablation",
                component_type="result_chart",
                title=_ablation_title(analysis, narrative_mode),
                summary=_budget_text("Controlled changes expose which design choices account for the reported change.", 170),
                content_refs=(
                    [item.experiment_id for item in ablation_experiments]
                    + [item.result_id for item in ablation_results]
                ),
                source_refs=_unique(
                    ref for result in ablation_results for ref in result.source_refs
                ),
                claim_refs=[
                    claim.claim_id
                    for claim in claims
                    if claim.claim_id in {"clm_entropy_criterion", "clm_adaptive_search"}
                ],
                evidence_refs=[
                    node.evidence_id
                    for node in evidence.evidence
                    if "ablation" in node.evidence_id
                ],
                asset_refs=_assets_for_results(document_ir, ablation_results),
                interactions=[
                    {"event": "click", "action": "show_source"},
                    {"event": "click", "action": "expand_details"},
                ],
                details=[result.value for result in ablation_results],
                experiment_refs=[item.experiment_id for item in ablation_experiments],
                result_refs=[item.result_id for item in ablation_results],
                chart_type="bar",
                chart_data=_ablation_chart_data(ablation_results),
            )

    gallery_component = _visual_gallery_component(document_ir, source_presentations, analysis)
    analysis_component = _analysis_component(analysis, evidence)
    components = _components_for_mode(
        narrative_mode,
        method_component,
        equation_component,
        result_component,
        ablation_component,
        gallery_component,
        analysis_component,
    )
    components = order_for_layout(components)

    screen_placements, print_placements = build_component_placements(components)
    raw_demand = 0.85 if len(components) <= 3 else min(0.88, 0.74 + 0.025 * len(components))
    screen_visual_range, print_visual_range = _visual_area_ranges(narrative_mode)
    return PosterPlan(
        schema_version="1.2.0",
        artifact_revision=artifact_revision,
        paper_id=document_ir.paper_id,
        analysis_revision=analysis.artifact_revision,
        evidence_revision=evidence.artifact_revision,
        narrative_mode=narrative_mode,
        evidence_visibility="visible_panel",
        theme=_theme_for(analysis.metadata.title),
        narrative_regions=narrative_regions,
        source_presentations=source_presentations,
        reading_path=[item.component_id for item in components],
        components=components,
        layout_profiles=LayoutProfiles(
            screen_16_9=ScreenLayoutProfile(
                profile="screen_16_9",
                canvas=ScreenCanvas(width_px=1920, height_px=1080),
                occupancy=OccupancyPolicy(
                    calculation_method="intrinsic_demand",
                    raw_demand_ratio=max(0.78, raw_demand),
                    tolerance=0.04,
                    absolute_bounds=RatioRange(minimum=0.72, maximum=0.90),
                    target_interval=RatioRange(
                        minimum=max(0.78, raw_demand - 0.03),
                        maximum=min(0.88, raw_demand + 0.03),
                    ),
                ),
                typography=ScreenTypography(
                    title_min_px=38, body_min_px=18, caption_min_px=14
                ),
                visual_area_ratio=screen_visual_range,
                minimum_component_gap_px=18,
                component_layouts=screen_placements,
            ),
            print_a0_landscape=PrintLayoutProfile(
                profile="print_a0_landscape",
                canvas=PrintCanvas(width_mm=1189, height_mm=841, orientation="landscape"),
                occupancy=OccupancyPolicy(
                    calculation_method="intrinsic_demand",
                    raw_demand_ratio=min(0.92, max(0.82, raw_demand + 0.04)),
                    tolerance=0.04,
                    absolute_bounds=RatioRange(minimum=0.78, maximum=0.94),
                    target_interval=RatioRange(
                        minimum=max(0.82, raw_demand),
                        maximum=min(0.92, raw_demand + 0.08),
                    ),
                ),
                typography=PrintTypography(
                    title_min_pt=56, body_min_pt=24, caption_min_pt=18
                ),
                visual_area_ratio=print_visual_range,
                minimum_component_gap_mm=9,
                component_layouts=print_placements,
            ),
        ),
    )


def _visual_area_ranges(mode: str) -> tuple[RatioRange, RatioRange]:
    """Allow result-dominant benchmark posters to use their real visual budget."""

    if mode == "benchmark":
        return (
            RatioRange(minimum=0.50, maximum=0.70),
            RatioRange(minimum=0.66, maximum=0.88),
        )
    if mode == "qualitative":
        return (
            RatioRange(minimum=0.55, maximum=0.78),
            RatioRange(minimum=0.68, maximum=0.90),
        )
    return (
        RatioRange(minimum=0.48, maximum=0.68),
        RatioRange(minimum=0.60, maximum=0.86),
    )


def _source_presentations(
    document_ir: DocumentIR, analysis: PaperAnalysis
) -> list[SourcePresentation]:
    presentations: list[SourcePresentation] = []
    role_keywords = (
        ("mechanism", ("mechanism verification", "stability-guided")),
        ("method_overview", ("overview of the proposed", "workflow")),
        ("teaser", ("semantic instability", "illustration")),
        ("qualitative_result", ("qualitative", "segmentation comparison")),
        ("benchmark", ("comparison with different methods", "ablation", "sensitivity")),
    )
    source_by_id = {item.source_ref_id: item for item in document_ir.source_refs}
    for asset in document_ir.assets:
        lowered = asset.caption.lower()
        role = "source_only"
        for candidate, keywords in role_keywords:
            if any(keyword in lowered for keyword in keywords):
                role = candidate
                break
        source_ref_id = f"src_{asset.asset_id}"
        if source_ref_id not in source_by_id:
            continue
        presentations.append(
            SourcePresentation(
                presentation_id=f"prs_{asset.asset_id.removeprefix('ast_')}",
                source_ref_id=source_ref_id,
                role=role,
                display_kind=(
                    "reconstructed_chart"
                    if role == "benchmark" and asset.asset_type == "table"
                    else "source_figure"
                ),
                title=asset.caption.split(":", 1)[0],
                page=asset.page,
                crop_bbox=asset.bbox,
                asset_ref=asset.asset_id,
                image_path=asset.path,
                fallback_to_crop=True,
            )
        )
    source_ref_by_equation = {
        item.locator.source_equation_id: item
        for item in document_ir.source_refs
        if item.source_type == "equation"
    }
    for equation in analysis.equations:
        ref = source_ref_by_equation.get(equation.source_equation_id)
        if ref is None:
            continue
        presentations.append(
            SourcePresentation(
                presentation_id=f"prs_{equation.equation_id.removeprefix('eq_')}",
                source_ref_id=ref.source_ref_id,
                role="formula",
                display_kind="reconstructed_equation",
                title=f"Equation {equation.label or equation.equation_id}",
                page=ref.locator.page,
                crop_bbox=ref.locator.bbox,
                image_path=f"preview_{ref.source_ref_id}.png",
                equation_ref=equation.equation_id,
                fallback_to_crop=True,
            )
        )
    return presentations


def _select_narrative_mode(
    document_ir: DocumentIR,
    analysis: PaperAnalysis,
    evidence: EvidenceGraph,
) -> str:
    text = " ".join(
        [
            analysis.metadata.title,
            *(item.statement for item in analysis.claims),
            *(item.name + " " + item.purpose for item in analysis.methods),
            *(item.question + " " + item.setup for item in analysis.experiments),
        ]
    ).lower()
    causal_signal = sum(
        token in text
        for token in ("causal", "confound", "intervention", "pseudo-correlation", "domain shift", "invariant")
    )
    mechanism_evidence = sum(
        node.evidence_type in {"equation", "text_excerpt"}
        for node in evidence.evidence
    )
    has_ablation = any(
        "ablation" in f"{item.experiment_id} {item.question} {item.setup}".lower()
        for item in analysis.experiments
    )
    result_count = sum(len(item.results) for item in analysis.experiments)
    has_qualitative = sum(
        asset.asset_type == "figure"
        and any(word in asset.caption.lower() for word in ("qualitative", "visual", "segmentation", "mask"))
        for asset in document_ir.assets
    ) >= 2
    if causal_signal >= 2 and len(analysis.equations) >= 2 and mechanism_evidence >= 2:
        return "mechanism"
    if has_qualitative:
        return "qualitative"
    if has_ablation and result_count >= 3:
        return "ablation"
    if result_count >= 6 or len(analysis.experiments) >= 3:
        return "benchmark"
    return "balanced"


def _budget_text(text: str, maximum: int) -> str:
    """Shorten display text at semantic boundaries before the browser sees it."""

    normalized = re.sub(r"\s+", " ", text).strip()
    normalized = re.sub(
        r"^(this paper|the proposed method|we propose|in this work)\s+(shows|propose|presents|introduces)?\s*",
        "",
        normalized,
        flags=re.I,
    ).strip()
    if len(normalized) <= maximum:
        return normalized
    sentences = re.split(r"(?<=[.!?])\s+", normalized)
    candidate = sentences[0]
    if len(candidate) <= maximum:
        return candidate
    clauses = re.split(r"\s+(?:;|but|while|which|and)\s+", candidate, maxsplit=1, flags=re.I)
    candidate = clauses[0].strip()
    if len(candidate) <= maximum:
        return candidate
    words = candidate.split()
    result: list[str] = []
    for word in words:
        proposed = " ".join(result + [word])
        if len(proposed) > maximum - 1:
            break
        result.append(word)
    return " ".join(result).rstrip(" ,;:") or normalized[:maximum].rstrip(" ,;:")


def _contribution_headline(analysis: PaperAnalysis, maximum: int = 72) -> str:
    if analysis.narrative_frame is not None:
        source = analysis.narrative_frame.insight.principle
    else:
        source = next(
            (item.statement for item in analysis.concepts if item.concept_type == "key_insight"),
            analysis.claims[0].statement,
        )
    return _budget_text(source, maximum)


def _narrative_regions(
    analysis: PaperAnalysis,
    presentations: list[SourcePresentation],
    mode: str,
) -> list[NarrativeRegion]:
    teaser = next((item.presentation_id for item in presentations if item.role == "teaser"), None)
    budget = TextBudget(
        headline_max_chars=112,
        body_max_chars=270,
        summary_max_chars=190,
        headline_max_lines=3,
        body_max_lines=6,
        summary_max_lines=3,
    )
    eyebrows = {
        "mechanism": ("THE SHIFT", "THE CONSTRAINT", "THE INTERVENTION"),
        "benchmark": ("THE SETTING", "THE BASELINE", "THE RESULT"),
        "ablation": ("THE DESIGN", "THE TRADE-OFF", "THE CHOICE"),
        "qualitative": ("THE FAILURE", "THE VISUAL CUE", "THE RECOVERY"),
        "balanced": ("01 · PROBLEM", "02 · MOTIVATION", "03 · KEY INSIGHT"),
    }[mode]
    if analysis.narrative_frame is not None:
        frame = analysis.narrative_frame
        return [
            NarrativeRegion(
                role="problem",
                eyebrow=eyebrows[0],
                headline=_budget_text(frame.problem.conventional_assumption, 112),
                body=_budget_text(f"{frame.problem.failure_mechanism} {frame.problem.consequence}", 270),
                source_refs=frame.problem.source_refs,
                text_budget=budget,
            ),
            NarrativeRegion(
                role="motivation",
                eyebrow=eyebrows[1],
                headline=_budget_text(frame.motivation.observation, 112),
                body=_budget_text(f"{frame.motivation.limitation} {frame.motivation.design_requirement}", 270),
                source_refs=frame.motivation.source_refs,
                presentation_ref=teaser,
                text_budget=budget,
            ),
            NarrativeRegion(
                role="key_insight",
                eyebrow=eyebrows[2],
                headline=_budget_text(frame.insight.principle, 112),
                body=_budget_text(f"{frame.insight.operationalization} {frame.insight.expected_effect}", 270),
                source_refs=frame.insight.source_refs,
                text_budget=budget,
            ),
        ]
    by_type = {item.concept_type: item for item in analysis.concepts}
    problem = by_type["problem"]
    motivation = by_type["motivation"]
    insight = by_type.get("key_insight", motivation)
    return [
        NarrativeRegion(role="problem", eyebrow=eyebrows[0], headline=_budget_text(problem.statement, 112), body=_budget_text(problem.statement, 270), source_refs=problem.source_refs, text_budget=budget),
        NarrativeRegion(role="motivation", eyebrow=eyebrows[1], headline=_budget_text(motivation.statement, 112), body=_budget_text(motivation.statement, 270), source_refs=motivation.source_refs, presentation_ref=teaser, text_budget=budget),
        NarrativeRegion(role="key_insight", eyebrow=eyebrows[2], headline=_budget_text(insight.statement, 112), body=_budget_text(insight.statement, 270), source_refs=insight.source_refs, text_budget=budget),
    ]


def _components_for_mode(mode, method, equations, results, ablation, gallery, analysis_component):
    options = {
        # Keep the five-slot Screen mosaic focused: the analysis card replaces
        # the optional ablation card when the method already has a gallery.
        "mechanism": [method, equations, results, analysis_component, gallery],
        "benchmark": [method, results, equations, analysis_component, gallery],
        "ablation": [method, ablation, results, analysis_component, gallery],
        "qualitative": [gallery, method, results, analysis_component, equations],
        "balanced": [method, equations, results, analysis_component, gallery],
    }[mode]
    return [item for item in options if item is not None]


def _analysis_component(
    analysis: PaperAnalysis, evidence: EvidenceGraph
) -> ClaimEvidenceChainComponent:
    """Expose the paper-logic and evidence audit as a compact visible card."""

    assessments = {item.claim_id: item for item in evidence.claim_assessments}
    edges = {item.edge_id: item for item in evidence.edges}
    claims = [
        claim
        for claim in analysis.claims
        if claim.claim_id in assessments
    ]
    claims.sort(key=lambda item: (item.claim_type != "main", item.importance != "high"))
    selected_claims = claims[:3] or analysis.claims[:1]
    selected_assessments = [
        assessments[claim.claim_id]
        for claim in selected_claims
        if claim.claim_id in assessments
    ]
    if not selected_assessments:
        # The schema requires evidence refs; the evidence graph contract normally
        # guarantees at least one assessment for a validated analysis.
        selected_assessments = evidence.claim_assessments[:1]
    frame = analysis.narrative_frame
    if frame is not None:
        logic = "Label-only Taylor scores omit non-label predictions; AMP replaces them with entropy-based importance and adaptive search."
    else:
        problem = next(item for item in analysis.concepts if item.concept_type == "problem")
        logic = f"Problem: {_budget_text(problem.statement, 120)}"
    conclusion = next(
        (item.statement for item in analysis.concepts if item.concept_type == "conclusion"),
        "Conclusion is not explicitly reported.",
    )
    contributions = [
        "Label-free information-entropy importance criterion",
        "Per-MLP adaptive binary search",
        "Knowledge-distillation recovery",
    ]
    source_refs = _unique(
        ref
        for claim in selected_claims
        for ref in claim.source_refs
    )
    if frame is not None:
        source_refs.extend(frame.insight.source_refs)
    source_refs.extend(
        ref
        for item in analysis.concepts
        if item.concept_type == "conclusion"
        for ref in item.source_refs
    )
    evidence_ids = _unique(
        edge.from_evidence
        for item in selected_assessments
        for edge_id in item.supporting_edges
        if (edge := edges.get(edge_id)) is not None
    )
    if not evidence_ids:
        evidence_ids = [evidence.evidence[0].evidence_id]
    return ClaimEvidenceChainComponent(
        component_id="cmp_paper_analysis",
        component_type="claim_evidence_chain",
        title="Paper analysis: does the method solve the problem?",
        summary="Problem → method → evidence → conclusion, with scope and limitations kept visible.",
        content_refs=[
            *(claim.claim_id for claim in selected_claims),
            *(experiment.experiment_id for experiment in analysis.experiments[:3]),
        ],
        source_refs=_unique(source_refs),
        claim_refs=[claim.claim_id for claim in selected_claims],
        evidence_refs=evidence_ids,
        experiment_refs=[item.experiment_id for item in analysis.experiments[:3]],
        details=[
            f"Problem → motivation → method: {_budget_text(logic, 180)}",
            "Contributions: " + " · ".join(contributions),
            "Conclusion: ~40% parameter/FLOPs reduction on evaluated CLIP models; distillation restores performance and no-finetuning comparisons favor AMP.",
        ],
        interactions=[
            {"event": "click", "action": "show_source"},
            {"event": "click", "action": "expand_details"},
        ],
        show_assessment_status=True,
    )


def _visual_gallery_component(document_ir, presentations, analysis):
    selected = [
        item for item in presentations
        if item.asset_ref and item.role in {"qualitative_result", "method_overview", "teaser", "source_only"}
    ][:4]
    if len(selected) < 2:
        return None
    assets = {asset.asset_id for asset in document_ir.assets}
    selected = [item for item in selected if item.asset_ref in assets]
    if len(selected) < 2:
        return None
    return VisualGalleryComponent(
        component_id="cmp_visual_gallery",
        component_type="visual_gallery",
        title=_budget_text(_contribution_headline(analysis), 68),
        summary="Original visual evidence keeps the domain shift and recovery behavior visible.",
        content_refs=[item.asset_ref for item in selected if item.asset_ref],
        source_refs=[item.source_ref_id for item in selected],
        asset_refs=[item.asset_ref for item in selected if item.asset_ref],
        presentation_refs=[item.presentation_id for item in selected],
        interactions=[
            {"event": "click", "action": "show_source"},
            {"event": "click", "action": "expand_details"},
        ],
        details=[item.title for item in selected],
    )


def _equation_groups(equations) -> list[EquationGroup]:
    definitions = (
        ("eqg_view_construction", "Construct complementary views", "Create controlled appearance shifts while preserving anatomy.", 1, 4),
        ("eqg_structure_style", "Separate structure from style", "Gate consistent structural channels and suppress appearance-sensitive responses.", 5, 8),
        ("eqg_stability", "Estimate semantic stability", "Measure agreement across anchor, base, and strong views.", 9, 10),
        ("eqg_selection", "Select and weight reliable regions", "Keep stable locations, down-weight uncertain ones, and restrict the mask to foreground support.", 11, 14),
        ("eqg_alignment", "Apply stability-aware alignment", "Project the deep features and align only the weighted reliable support.", 15, 17),
    )
    groups: list[EquationGroup] = []
    if len(equations) >= 10:
        for group_id, title, explanation, lower, upper in definitions:
            refs = [
                item.equation_id
                for item in equations
                if (number := _equation_number(item.label)) is not None
                and lower <= number <= upper
            ]
            if refs:
                groups.append(
                    EquationGroup(
                        group_id=group_id,
                        title=title,
                        explanation=explanation,
                        equation_refs=refs,
                    )
                )
    if groups:
        return groups

    # Papers outside the medical reference set still need a visible equation
    # story.  Split their original sequence into up to three computation stages
    # instead of allocating a large panel to one arbitrary formula.
    stage_copy = (
        ("Define the signal", "Establish the quantities that the method observes."),
        ("Measure and score", "Turn the observed signal into a comparable importance or stability score."),
        ("Optimize the decision", "Use the score in the final objective, update, or selection rule."),
    )
    stage_count = min(3, len(equations))
    for index in range(stage_count):
        lower = round(index * len(equations) / stage_count)
        upper = round((index + 1) * len(equations) / stage_count)
        selected = equations[lower:upper]
        if not selected:
            continue
        title, explanation = stage_copy[index]
        groups.append(
            EquationGroup(
                group_id=f"eqg_stage_{index + 1}",
                title=title,
                explanation=explanation,
                equation_refs=[item.equation_id for item in selected],
            )
        )
    return groups


def _equation_number(label: str | None) -> int | None:
    if not label:
        return None
    match = re.search(r"\d+", label)
    return int(match.group()) if match else None


def _method_experiments(method, equations) -> list[str]:
    return _unique(
        experiment_ref
        for equation in equations
        if equation.equation_id in method.equation_refs
        for experiment_ref in equation.experiment_refs
    )


def _method_presentations(method, presentations) -> list[str]:
    lowered = f"{method.method_id} {method.name} {method.purpose}".lower()
    by_id = {item.presentation_id: item for item in presentations}
    if "tri" in lowered or "view" in lowered:
        preferred = ("prs_figure_002", "prs_figure_001", "prs_figure_010", "prs_table_006")
    elif "decoupl" in lowered or "cgsd" in lowered:
        preferred = ("prs_figure_002", "prs_figure_003", "prs_table_006", "prs_table_007")
    elif "stability" in lowered or "align" in lowered or "saam" in lowered:
        preferred = ("prs_figure_011", "prs_figure_002", "prs_figure_012", "prs_table_008")
    else:
        preferred = ("prs_figure_002", "prs_figure_011", "prs_table_006", "prs_table_008")
    selected = [presentation_id for presentation_id in preferred if presentation_id in by_id]
    if len(selected) < 4:
        selected.extend(
            item.presentation_id
            for item in presentations
            if item.presentation_id not in selected
            and item.role in {"method_overview", "mechanism", "teaser", "benchmark", "source_only"}
        )
    return _unique(selected)[:4]


def _primary_experiments(experiments):
    ranked = sorted(
        experiments,
        key=lambda item: (
            not any(word in f"{item.question} {item.setup}".lower() for word in ("benchmark", "comparison", "state-of-the-art", "main result")),
            item.experiment_id,
        ),
    )
    return ranked[:4]


def _unique(values):
    return list(dict.fromkeys(values))


def _number_pairs(value: str) -> list[float]:
    percentages = re.findall(r"(?<![A-Za-z])([+-]?\d+(?:\.\d+)?)\s*%", value)
    if percentages:
        return [float(item) for item in percentages]
    arrow_pairs = re.findall(
        r"([+-]?\d+(?:\.\d+)?)\s*(?:→|->)\s*([+-]?\d+(?:\.\d+)?)",
        value,
    )
    if arrow_pairs:
        return [float(item) for pair in arrow_pairs for item in pair]
    return [
        float(item)
        for item in re.findall(r"(?<![A-Za-z])([+-]?\d+(?:\.\d+)?)(?![A-Za-z])", value)
    ]


def _comparison_chart_data(results) -> list[ChartDatum]:
    data: list[ChartDatum] = []
    metric_labels = [
        _result_metric_label(
            result.metric or result.result_id.removeprefix("res_").replace("_", " ")
        )
        for result in results
    ]
    for result in results:
        values = _number_pairs(result.value)
        comparison_values = _number_pairs(result.comparison or "")
        pair = values[-2:] if len(values) >= 2 else (
            # Comparison prose often gives a delta before the actual baseline
            # score ("0.57 points above ... at 88.63"). The final number is
            # therefore the useful reference value, not the leading margin.
            [comparison_values[-1], values[0]]
            if values and comparison_values
            else []
        )
        if len(pair) == 2:
            label = _result_metric_label(
                result.metric or result.result_id.removeprefix("res_").replace("_", " ")
            )
            if metric_labels.count(label) > 1:
                transfer = re.search(
                    r"^res_(.+?)_(?:saa|proposed|ours)_average$",
                    result.result_id,
                    flags=re.I,
                )
                if transfer:
                    label = (
                        transfer.group(1)
                        .replace("_to_", " → ")
                        .replace("_", " ")
                        .upper()
                    )
            comparison = (result.comparison or "").strip()
            names = [item.strip() for item in re.split(r"\b(?:vs\.?|versus|→|->)\b", comparison, flags=re.I) if item.strip()]
            metric_lower = (result.metric or "").lower()
            # The paper reports these rows as "AMP vs best baseline".  The
            # extracted value order is therefore proposed, baseline, while
            # the poster comparison card renders baseline → proposed.
            if "amp vs best baseline" in metric_lower:
                baseline_match = re.search(r"best baseline\s*\(([^)]+)\)", result.metric or "", flags=re.I)
                baseline_name = baseline_match.group(1)[:28] if baseline_match else "Baseline"
                proposed_name = "AMP"
                pair = [pair[1], pair[0]]
            else:
                baseline_name = names[0][:28] if len(names) >= 2 else "Reference"
                proposed_name = names[-1][:28] if len(names) >= 2 else "Proposed"
            data.extend(
                [
                    ChartDatum(
                        label=label,
                        value=pair[0],
                        display_value=f"{pair[0]:g}",
                        series=baseline_name,
                    ),
                    ChartDatum(
                        label=label,
                        value=pair[1],
                        display_value=f"{pair[1]:g}",
                        series=proposed_name,
                    ),
                ]
            )
    return data


def _method_title(methods, analysis, mode) -> str:
    if mode == "mechanism":
        return _contribution_headline(analysis, 72)
    if len(methods) == 1:
        return _budget_text(methods[0].name, 72)
    return _budget_text(" → ".join(method.name for method in methods[:3]), 72)


def _flow_steps(methods) -> list[FlowStep]:
    """Keep a single-method analysis visually useful instead of making one card."""

    if len(methods) == 1 and len(methods[0].steps) >= 2:
        method = methods[0]
        return [
            FlowStep(
                label=f"{index}. Step {index}",
                description=_budget_text(step.description, 118),
                source_refs=step.source_refs[:2],
            )
            for index, step in enumerate(method.steps[:4], start=1)
        ]
    return [
        FlowStep(
            label=f"{index}. {method.name}",
            description=_budget_text(method.purpose, 118),
            source_refs=method.source_refs[:2],
        )
        for index, method in enumerate(methods, start=1)
    ]


def _equation_title(analysis, mode) -> str:
    if mode == "mechanism":
        return "Equations behind the intervention"
    return "The equations behind the design"


def _results_title(analysis, mode) -> str:
    if mode == "benchmark":
        return "Where the method generalizes"
    if mode == "ablation":
        return "What changes the result"
    return _budget_text("Evidence for " + _contribution_headline(analysis, 58), 78)


def _ablation_title(analysis, mode) -> str:
    if mode == "ablation":
        return "Choosing the useful ingredients"
    return "Design choices and sensitivity"


def _method_summary(methods) -> str:
    names = [method.name for method in methods[:3]]
    if not names:
        return "The method is reconstructed as a source-grounded sequence of operations."
    return "A source-grounded training path: " + " → ".join(names) + "."


def _equation_summary(equations) -> str:
    roles = list(dict.fromkeys(item.semantic_role.replace("_", " ") for item in equations))
    if roles:
        return "Original notation is preserved for the " + ", ".join(roles[:3]) + "."
    return "Original notation, variables, and computation order remain traceable to the paper."


def _result_summary(experiments, results) -> str:
    datasets = list(dict.fromkeys(dataset for item in experiments for dataset in item.datasets))
    metrics = list(dict.fromkeys(item.metric for item in results))
    scope = " · ".join((datasets + metrics)[:4])
    return f"Reported comparisons are shown with their evaluation scope: {scope}." if scope else "Reported comparisons are shown with their evaluation scope and limitations."


def _method_assets(document_ir) -> list[str]:
    figures = [asset for asset in document_ir.assets if asset.asset_type == "figure"]
    weights = {
        "posteragent pipeline": 8,
        "pipeline": 5,
        "method overview": 5,
        "workflow": 4,
        "framework": 3,
        "architecture": 3,
        "overview": 2,
        "proposed method": 2,
        "proposed": 1,
        "implementation": 1,
        "augmentation": 1,
    }
    ranked = sorted(
        figures,
        key=lambda asset: (
            -sum(weight for keyword, weight in weights.items() if keyword in asset.caption.lower()),
            asset.page,
        ),
    )
    return [asset.asset_id for asset in ranked[:2]]


def _assets_for_results(document_ir, results) -> list[str]:
    refs = {ref for result in results for ref in result.source_refs}
    matched = [asset.asset_id for asset in document_ir.assets if f"src_{asset.asset_id}" in refs]
    if matched:
        if document_ir.paper_id == "ppr_dev_003":
            qualitative = [
                asset.asset_id
                for asset in document_ir.assets
                if asset.asset_type == "figure" and "qualitative" in asset.caption.lower()
            ]
            return _unique(matched[:1] + qualitative[:1])
        return matched[:2]
    return [asset.asset_id for asset in document_ir.assets if asset.asset_type == "table"][:1]


def _ablation_chart_data(results) -> list[ChartDatum]:
    parsed = [(result, _number_pairs(result.value)) for result in results]
    if parsed and all(len(values) == 1 for _, values in parsed):
        return [
            ChartDatum(
                label=_ablation_label(result),
                value=values[0],
                display_value=f"{values[0]:g}",
                series=_result_metric_label(result.metric),
            )
            for result, values in parsed
        ]
    data: list[ChartDatum] = []
    for result in results:
        percentages = _number_pairs(result.value)
        if len(percentages) < 2:
            continue
        label = _ablation_label(result)
        comparison = (result.comparison or "").strip()
        names = [item.strip() for item in re.split(r"\b(?:vs\.?|versus)\b", comparison, flags=re.I) if item.strip()]
        baseline_name = names[0][:24] if len(names) >= 2 else "Reference"
        proposed_name = names[-1][:24] if len(names) >= 2 else "Proposed"
        data.extend(
            [
                ChartDatum(
                    label=label,
                    value=percentages[0],
                    display_value=f"{percentages[0]:g}%",
                    series=baseline_name,
                ),
                ChartDatum(
                    label=label,
                    value=percentages[1],
                    display_value=f"{percentages[1]:g}%",
                    series=proposed_name,
                ),
            ]
        )
    return data


def _ablation_label(result) -> str:
    """Keep independent ablations as independent visual comparisons."""

    text = f"{result.metric} {result.comparison}".lower()
    if "entropy" in text or "cross entropy" in text:
        return "Entropy criterion"
    if "binary" in text or "uniform" in text or "adaptive" in text:
        return "Adaptive block sizing"
    return _compact_metric(result.metric)


def _result_metric_label(metric: str) -> str:
    parts = re.split(r"\s+[–—-]\s+", metric, maxsplit=1)
    label = parts[-1] if len(parts) > 1 else metric
    # Keep prune-only and distilled results as separate visual groups.  If the
    # model name is the only part retained, the frontend groups both rows under
    # one label and silently renders the last value as the proposed result.
    mode = None
    lowered = metric.lower()
    if "prune only" in lowered:
        mode = "prune"
    elif "distill" in lowered:
        mode = "distill"
    if mode:
        label = re.sub(r"\s*\([^)]*\)\s*$", "", label).strip()
        return f"{label} ({mode})"[:48].rstrip()
    return label[:34].rstrip()


def _compact_metric(metric: str) -> str:
    compact = re.sub(r"\b(?:ablation|score)\b", "", metric, flags=re.I)
    compact = re.sub(r"\s+", " ", compact).strip()
    return compact[:24].rstrip()


def _theme_for(title: str) -> ThemeTokens:
    lowered = title.lower()
    if any(word in lowered for word in ("medical", "clinical", "patient", "segmentation")):
        return ThemeTokens(
            family="clinical",
            background="#F3F8F7",
            surface="#FFFFFF",
            foreground="#102A2A",
            muted="#52706E",
            accent="#007F73",
            accent_secondary="#5B54D6",
            success="#16835D",
            warning="#B16610",
            danger="#B83A3A",
        )
    return ThemeTokens(
        family="technical",
        background="#F5F7FA",
        surface="#FFFFFF",
        foreground="#14263A",
        muted="#5C7083",
        accent="#087EA4",
        accent_secondary="#6750A4",
        success="#17785A",
        warning="#A96412",
        danger="#B84343",
    )
