from __future__ import annotations

import copy
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from papercraft.api import create_app
from papercraft.models import DocumentIR, EvidenceGraph, NarrativePlan, PaperAnalysis, PosterPlan
from papercraft.service import PaperCraftService
from papercraft.validation import validate_narrative_plan


def _shadow_payload(analysis, evidence, archetype="method_pipeline"):
    main_claims = [item for item in analysis.claims if item.claim_type == "main"]
    claim = main_claims[0]
    assessment = next(
        item for item in evidence.claim_assessments if item.claim_id == claim.claim_id
    )
    evidence_id = next(
        (
            edge.from_evidence
            for edge in evidence.edges
            if edge.to_claim == claim.claim_id
        ),
        evidence.evidence[0].evidence_id,
    )
    evidence_node = next(item for item in evidence.evidence if item.evidence_id == evidence_id)
    problem = next(item for item in analysis.concepts if item.concept_type == "problem")
    insight = next(
        (item for item in analysis.concepts if item.concept_type == "key_insight"),
        analysis.concepts[0],
    )
    method = analysis.methods[0]
    nodes = [
        {
            "node_id": "nar_problem",
            "role": "problem",
            "statement": problem.statement,
            "importance": "primary",
            "object_refs": [problem.concept_id],
            "evidence_refs": [],
            "source_refs": problem.source_refs[:2],
        },
        {
            "node_id": "nar_insight",
            "role": "insight",
            "statement": insight.statement,
            "importance": "primary",
            "object_refs": [insight.concept_id],
            "evidence_refs": [],
            "source_refs": insight.source_refs[:2],
        },
        {
            "node_id": "nar_method",
            "role": "method",
            "statement": method.purpose,
            "importance": "primary",
            "object_refs": [method.method_id],
            "evidence_refs": [],
            "source_refs": method.source_refs[:2],
        },
        {
            "node_id": "nar_evidence",
            "role": "evidence",
            "statement": evidence_node.summary,
            "importance": "primary",
            "object_refs": [claim.claim_id],
            "evidence_refs": [evidence_id],
            "source_refs": evidence_node.source_refs[:2],
        },
    ]
    path = ["nar_problem", "nar_insight", "nar_method", "nar_evidence"]
    if assessment.status != "supported":
        nodes.append(
            {
                "node_id": "nar_boundary",
                "role": "boundary",
                "statement": assessment.limitations[0]
                if assessment.limitations
                else assessment.rationale,
                "importance": "primary",
                "object_refs": [claim.claim_id],
                "evidence_refs": [evidence_id],
                "source_refs": claim.source_refs[:2],
            }
        )
        path.append("nar_boundary")
    nodes.append(
        {
            "node_id": "nar_takeaway",
            "role": "takeaway",
            "statement": claim.statement,
            "importance": "primary",
            "object_refs": [claim.claim_id],
            "evidence_refs": [evidence_id],
            "source_refs": claim.source_refs[:2],
        }
    )
    path.append("nar_takeaway")
    relations = ["motivates", "operationalizes", "evaluated_by"]
    if assessment.status != "supported":
        relations.extend(["qualifies", "leads_to"])
    else:
        relations.append("supports")
    edges = [
        {
            "edge_id": f"nedge_{index}",
            "from_node": left,
            "to_node": right,
            "relation": relation,
            "transition": "The argument advances to the next grounded step.",
        }
        for index, (left, right, relation) in enumerate(
            zip(path, path[1:], relations), start=1
        )
    ]
    return {
        "archetype": archetype,
        "thesis": claim.statement,
        "archetype_rationale": "The primary contribution is organized as a scientific argument.",
        "nodes": nodes,
        "edges": edges,
        "primary_path": path,
        "claim_coverage": [
            {
                "claim_ref": item.claim_id,
                "disposition": "included" if item.claim_id == claim.claim_id else "omitted",
                "reason": "Primary story" if item.claim_id == claim.claim_id else "Secondary claim",
            }
            for item in main_claims
        ],
    }


class FakeAnthropicProvider:
    payload = None

    def __init__(self, ledger):
        self.ledger = ledger

    def generate(self, **kwargs):
        payload = copy.deepcopy(self.payload)
        if isinstance(payload.get("primary_path"), list):
            payload["primary_path"] = " -> ".join(payload["primary_path"])
        payload["evidence_nodes"] = [
            node for node in payload["nodes"] if node["role"] == "evidence"
        ]
        payload["nodes"] = [
            node for node in payload["nodes"] if node["role"] != "evidence"
        ]
        return SimpleNamespace(
            value=kwargs["output_model"].model_validate(payload)
        )


def test_narrate_stage_revisions_optional_artifact_without_changing_poster(
    project_root, tmp_path, monkeypatch
):
    service = PaperCraftService(project_root, runtime_root=tmp_path / "runtime")
    job = service.bootstrap_amp_demo()
    analysis = service.artifacts.load(job["job_id"], "paper_analysis")
    evidence = service.artifacts.load(job["job_id"], "evidence_graph")
    poster_before = service.artifacts.load(job["job_id"], "poster_plan")
    assert isinstance(poster_before, PosterPlan)
    FakeAnthropicProvider.payload = _shadow_payload(analysis, evidence)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    monkeypatch.setattr("papercraft.service.AnthropicStructuredProvider", FakeAnthropicProvider)

    first = service.narrate_with_model(job["job_id"])
    second = service.narrate_with_model(job["job_id"])

    assert (first.artifact_revision, second.artifact_revision) == (1, 2)
    assert service.store.get_job(job["job_id"]).status == "poster_ready"
    assert service.artifacts.load(job["job_id"], "poster_plan") == poster_before
    assert service.artifacts.bundle(job["job_id"])["narrative_plan"]["artifact_revision"] == 2


def test_failed_shadow_narration_does_not_save_or_change_job_status(
    project_root, tmp_path, monkeypatch
):
    class FailingProvider:
        def __init__(self, ledger):
            pass

        def generate(self, **kwargs):
            raise RuntimeError("invalid narrative")

    service = PaperCraftService(project_root, runtime_root=tmp_path / "runtime")
    job = service.bootstrap_amp_demo(job_id="failed_narrative")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    monkeypatch.setattr("papercraft.service.AnthropicStructuredProvider", FailingProvider)

    with pytest.raises(RuntimeError, match="invalid narrative"):
        service.narrate_with_model(job["job_id"])
    assert service.store.get_job(job["job_id"]).status == "poster_ready"
    assert not service.artifacts.has(job["job_id"], "narrative_plan")


def test_narrate_api_stage_returns_optional_plan(project_root, tmp_path, monkeypatch):
    client = TestClient(create_app(project_root, runtime_root=tmp_path / "runtime"))
    created = client.post("/api/demo").json()
    service = client.app.state.service
    analysis = service.artifacts.load(created["job_id"], "paper_analysis")
    evidence = service.artifacts.load(created["job_id"], "evidence_graph")
    FakeAnthropicProvider.payload = _shadow_payload(analysis, evidence)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    monkeypatch.setattr("papercraft.service.AnthropicStructuredProvider", FakeAnthropicProvider)

    response = client.post(f"/api/jobs/{created['job_id']}/run/narrate")
    assert response.status_code == 200
    assert response.json()["archetype"] == "method_pipeline"
    bundle = client.get(f"/api/jobs/{created['job_id']}/bundle").json()
    assert "narrative_plan" in bundle


def test_visual_direction_reorders_only_within_existing_layout_and_is_persisted(
    project_root, tmp_path
):
    service = PaperCraftService(project_root, runtime_root=tmp_path / "runtime")
    job = service.bootstrap_amp_demo()
    analysis = service.artifacts.load(job["job_id"], "paper_analysis")
    evidence = service.artifacts.load(job["job_id"], "evidence_graph")
    baseline = service.artifacts.load(job["job_id"], "poster_plan")
    assert isinstance(baseline, PosterPlan)
    narrative = NarrativePlan(
        schema_version="1.0.0",
        artifact_revision=1,
        paper_id=job["paper_id"],
        analysis_revision=analysis.artifact_revision,
        evidence_revision=evidence.artifact_revision,
        **_shadow_payload(analysis, evidence),
    )
    service.artifacts.save(job["job_id"], "narrative_plan", narrative)

    visual, directed = service.direct(job["job_id"])

    assert visual.status == "applied"
    assert visual.visual_archetype == "pipeline_story"
    assert visual.component_sequence == directed.reading_path
    assert directed.artifact_revision == baseline.artifact_revision + 1
    assert {item.component_id for item in directed.components} == {
        item.component_id for item in baseline.components
    }
    assert [item.role for item in directed.narrative_regions] == [
        "problem", "motivation", "key_insight"
    ]
    for profile in (
        directed.layout_profiles.screen_16_9,
        directed.layout_profiles.print_a0_landscape,
    ):
        assert {item.component_id for item in profile.component_layouts} == set(
            directed.reading_path
        )
    for baseline_profile, directed_profile in (
        (
            baseline.layout_profiles.screen_16_9,
            directed.layout_profiles.screen_16_9,
        ),
        (
            baseline.layout_profiles.print_a0_landscape,
            directed.layout_profiles.print_a0_landscape,
        ),
    ):
        baseline_slots = sorted(
            (
                item.order,
                item.column_start,
                item.column_span,
                item.row_start,
                item.row_span,
                item.minimum_height,
                item.preferred_height,
            )
            for item in baseline_profile.component_layouts
        )
        directed_slots = sorted(
            (
                item.order,
                item.column_start,
                item.column_span,
                item.row_start,
                item.row_span,
                item.minimum_height,
                item.preferred_height,
            )
            for item in directed_profile.component_layouts
        )
        assert directed_slots == baseline_slots
    bundle = service.artifacts.bundle(job["job_id"])
    assert bundle["visual_plan"]["visual_archetype"] == "pipeline_story"


def test_direct_api_requires_narrative_plan(project_root, tmp_path):
    client = TestClient(create_app(project_root, runtime_root=tmp_path / "runtime"))
    created = client.post("/api/demo").json()
    response = client.post(f"/api/jobs/{created['job_id']}/run/direct")
    assert response.status_code == 409
    assert "NarrativePlan" in response.json()["detail"]


@pytest.mark.parametrize(
    ("paper_id", "expected_archetype"),
    [
        ("ppr_dev_001", "method_pipeline"),
        ("ppr_dev_002", "causal_intervention"),
        ("ppr_dev_003", "mechanism"),
    ],
)
def test_gold_papers_accept_expected_shadow_narrative_contract(
    project_root, paper_id, expected_archetype
):
    root = project_root / "evaluation" / "papers" / paper_id / "annotations"
    document = DocumentIR.model_validate_json((root / "document_ir.gold.json").read_text())
    analysis = PaperAnalysis.model_validate_json((root / "paper_analysis.gold.json").read_text())
    evidence = EvidenceGraph.model_validate_json((root / "evidence_graph.gold.json").read_text())
    payload = _shadow_payload(analysis, evidence, expected_archetype)
    from papercraft.models.narrative_plan import NarrativePlan

    plan = NarrativePlan(
        schema_version="1.0.0",
        artifact_revision=1,
        paper_id=paper_id,
        analysis_revision=analysis.artifact_revision,
        evidence_revision=evidence.artifact_revision,
        **payload,
    )
    validate_narrative_plan(document, analysis, evidence, plan)
    assert plan.archetype == expected_archetype
