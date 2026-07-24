from __future__ import annotations

import json

import pytest
from pydantic import ValidationError

from papercraft.models import DocumentIR, EvidenceGraph, PaperAnalysis, PosterPlan
from papercraft.planning import build_poster_plan
from papercraft.planning.deterministic_planner import _select_narrative_mode
from papercraft.review import ComponentRenderMetric, RenderMetrics, run_deterministic_review
from papercraft.validation import validate_artifact_set


def _gold(project_root):
    root = project_root / "evaluation" / "papers" / "ppr_dev_001" / "annotations"
    return (
        DocumentIR.model_validate_json((root / "document_ir.gold.json").read_text()),
        PaperAnalysis.model_validate_json((root / "paper_analysis.gold.json").read_text()),
        EvidenceGraph.model_validate_json((root / "evidence_graph.gold.json").read_text()),
    )


def test_amp_gold_builds_all_component_families_and_passes_six_reviewers(project_root):
    document, analysis, evidence = _gold(project_root)
    plan = build_poster_plan(document, analysis, evidence)
    assert {item.component_type for item in plan.components} == {
        "method_flow",
        "equation_explorer",
        "result_chart",
        "visual_gallery",
    }
    assert plan.evidence_visibility == "internal_only"
    assert "claim_evidence_chain" not in {item.component_type for item in plan.components}
    metrics = []
    for profile, occupied, visual, font, gap in (
        ("screen_16_9", 0.85, 0.60, 18, 18),
        ("print_a0_landscape", 0.88, 0.75, 24, 9),
    ):
        metrics.append(
            RenderMetrics(
                profile=profile,
                render_revision=1,
                occupied_area_ratio=occupied,
                visual_area_ratio=visual,
                reading_order_valid=True,
                density_imbalance=0,
                components=[
                    ComponentRenderMetric(
                        component_id=item.component_id,
                        minimum_font_size=font,
                        minimum_gap=gap,
                    )
                    for item in plan.components
                ],
            )
        )
    review = run_deterministic_review(
        document, analysis, evidence, plan, render_metrics=metrics
    )
    validate_artifact_set(document, analysis, evidence, plan, review)
    assert review.status == "passed"
    assert len(review.checker_summaries) == 6
    assert {item.severity for item in review.issues} <= {"warning"}


def test_layout_contract_rejects_overlap(project_root):
    document, analysis, evidence = _gold(project_root)
    payload = build_poster_plan(document, analysis, evidence).model_dump(mode="json")
    payload["layout_profiles"]["screen_16_9"]["component_layouts"][1]["column_start"] = 1
    with pytest.raises(ValidationError, match="overlap"):
        PosterPlan.model_validate(payload)


def test_stability_plan_exposes_narrative_inspectors_and_equation_chain(project_root):
    root = project_root / "evaluation" / "papers" / "ppr_dev_003" / "annotations"
    document = DocumentIR.model_validate_json((root / "document_ir.gold.json").read_text())
    analysis = PaperAnalysis.model_validate_json((root / "paper_analysis.gold.json").read_text())
    evidence = EvidenceGraph.model_validate_json((root / "evidence_graph.gold.json").read_text())
    plan = build_poster_plan(document, analysis, evidence)
    assert [item.role for item in plan.narrative_regions] == ["problem", "motivation", "key_insight"]
    method = next(item for item in plan.components if item.component_type == "method_flow")
    equations = next(item for item in plan.components if item.component_type == "equation_explorer")
    assert len(method.inspector_panels) == 3
    assert method.inspector_panels[-1].equation_refs == [f"eq_{i:02d}" for i in range(9, 18)]
    assert [group.group_id for group in equations.equation_groups][-3:] == [
        "eqg_stability", "eqg_selection", "eqg_alignment"
    ]
    assert any(item.role == "qualitative_result" for item in plan.source_presentations)


def test_legacy_poster_plan_defaults_keep_visible_evidence(valid_payloads):
    plan = PosterPlan.model_validate(valid_payloads["poster_plan"])
    assert plan.narrative_mode == "balanced"
    assert plan.evidence_visibility == "visible_panel"


def test_gold_planner_selects_distinct_narrative_modes(project_root):
    def load(paper_id):
        root = project_root / "evaluation" / "papers" / paper_id / "annotations"
        return tuple(
            model.model_validate_json((root / f"{name}.gold.json").read_text())
            for name, model in (
                ("document_ir", DocumentIR),
                ("paper_analysis", PaperAnalysis),
                ("evidence_graph", EvidenceGraph),
            )
        )

    amp_document, amp_analysis, amp_evidence = load("ppr_dev_001")
    qualitative_document, qualitative_analysis, qualitative_evidence = load("ppr_dev_003")

    assert _select_narrative_mode(amp_document, amp_analysis, amp_evidence) == "ablation"
    assert _select_narrative_mode(
        amp_document,
        amp_analysis.model_copy(
            update={
                "experiments": [
                    item
                    for item in amp_analysis.experiments
                    if "ablation" not in item.experiment_id
                ]
            }
        ),
        amp_evidence,
    ) == "benchmark"
    assert _select_narrative_mode(
        amp_document,
        amp_analysis.model_copy(update={"experiments": amp_analysis.experiments[:1]}),
        amp_evidence,
    ) == "balanced"
    assert _select_narrative_mode(
        qualitative_document, qualitative_analysis, qualitative_evidence
    ) == "qualitative"


def test_current_paper_plan_is_mechanism_and_budgeted(project_root):
    artifact_root = project_root / "runtime" / "jobs" / "job_ca4a21d8c2bb" / "artifacts"
    document = DocumentIR.model_validate_json(
        (artifact_root / "document_ir" / "r0001.json").read_text()
    )
    analysis = PaperAnalysis.model_validate_json(
        max((artifact_root / "paper_analysis").glob("*.json"), key=lambda path: path.stat().st_mtime).read_text()
    )
    evidence = EvidenceGraph.model_validate_json(
        max((artifact_root / "evidence_graph").glob("*.json"), key=lambda path: path.stat().st_mtime).read_text()
    )
    plan = build_poster_plan(document, analysis, evidence)
    assert plan.narrative_mode == "mechanism"
    assert plan.evidence_visibility == "internal_only"
    assert "claim_evidence_chain" not in {item.component_type for item in plan.components}
    assert all(region.text_budget is not None for region in plan.narrative_regions)
