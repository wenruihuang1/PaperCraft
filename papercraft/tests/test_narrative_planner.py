from __future__ import annotations

import copy
import json
from types import SimpleNamespace

import pytest
from jsonschema import Draft202012Validator
from pydantic import ValidationError

from papercraft.models import DocumentIR, EvidenceGraph, NarrativePlan, PaperAnalysis
from papercraft.planning import SemanticNarrativePlanner
from papercraft.validation import ArtifactReferenceError, validate_narrative_plan


def _minimal_artifacts(project_root):
    root = project_root / "tests" / "fixtures" / "valid" / "minimal"
    return (
        DocumentIR.model_validate_json((root / "document_ir.json").read_text()),
        PaperAnalysis.model_validate_json((root / "paper_analysis.json").read_text()),
        EvidenceGraph.model_validate_json((root / "evidence_graph.json").read_text()),
        NarrativePlan.model_validate_json((root / "narrative_plan.json").read_text()),
    )


class FakeProvider:
    def __init__(self, payload):
        self.payload = payload
        self.calls = []

    def generate(self, **kwargs):
        self.calls.append(kwargs)
        return SimpleNamespace(
            value=kwargs["output_model"].model_validate(copy.deepcopy(self.payload))
        )


def test_checked_in_narrative_schema_accepts_minimal_fixture(project_root):
    root = project_root / "tests" / "fixtures" / "valid" / "minimal"
    schema = json.loads(
        (project_root / "schemas" / "narrative_plan.schema.json").read_text()
    )
    payload = json.loads((root / "narrative_plan.json").read_text())
    Draft202012Validator.check_schema(schema)
    Draft202012Validator(schema).validate(payload)


def test_narrative_plan_rejects_duplicate_disconnected_cyclic_and_invalid_paths(
    project_root,
):
    *_, valid = _minimal_artifacts(project_root)
    payload = valid.model_dump(mode="json")

    duplicate = copy.deepcopy(payload)
    duplicate["nodes"][1]["node_id"] = duplicate["nodes"][0]["node_id"]
    with pytest.raises(ValidationError, match="duplicate narrative node ID"):
        NarrativePlan.model_validate(duplicate)

    disconnected = copy.deepcopy(payload)
    disconnected["nodes"].append(
        {
            "node_id": "nar_disconnected",
            "role": "claim",
            "statement": "A disconnected claim.",
            "importance": "supporting",
            "object_refs": ["clm_speed"],
            "evidence_refs": [],
            "source_refs": ["src_result"],
        }
    )
    with pytest.raises(ValidationError, match="weakly connected"):
        NarrativePlan.model_validate(disconnected)

    cyclic = copy.deepcopy(payload)
    cyclic["edges"].append(
        {
            "edge_id": "nedge_cycle",
            "from_node": "nar_takeaway",
            "to_node": "nar_problem",
            "relation": "leads_to",
            "transition": "This would create a cycle.",
        }
    )
    with pytest.raises(ValidationError, match="acyclic"):
        NarrativePlan.model_validate(cyclic)

    invalid_path = copy.deepcopy(payload)
    invalid_path["primary_path"][2] = "nar_evidence"
    invalid_path["primary_path"][3] = "nar_method"
    with pytest.raises(ValidationError, match="has no directed edge"):
        NarrativePlan.model_validate(invalid_path)


def test_cross_artifact_validation_rejects_unknown_refs_and_missing_claim_coverage(
    project_root,
):
    document, analysis, evidence, valid = _minimal_artifacts(project_root)
    validate_narrative_plan(document, analysis, evidence, valid)

    unknown = valid.model_copy(deep=True)
    unknown.nodes[0].object_refs = ["cpt_missing"]
    with pytest.raises(ArtifactReferenceError, match="UNKNOWN_SEMANTIC_REF"):
        validate_narrative_plan(document, analysis, evidence, unknown)

    missing = valid.model_copy(deep=True)
    missing.claim_coverage = []
    with pytest.raises(ArtifactReferenceError, match="MAIN_CLAIM_COVERAGE_MISSING"):
        validate_narrative_plan(document, analysis, evidence, missing)


def test_weak_main_claim_requires_matching_boundary_on_primary_path(project_root):
    document, analysis, evidence, valid = _minimal_artifacts(project_root)
    weak_evidence = evidence.model_copy(deep=True)
    weak_evidence.claim_assessments[0].status = "partially_supported"
    with pytest.raises(ArtifactReferenceError, match="EVIDENCE_BOUNDARY_MISSING"):
        validate_narrative_plan(document, analysis, weak_evidence, valid)


def test_semantic_planner_sends_only_semantic_json_and_selected_sources(project_root):
    document, analysis, evidence, valid = _minimal_artifacts(project_root)
    semantic_payload = valid.model_dump(mode="json")
    for field in (
        "schema_version",
        "artifact_revision",
        "paper_id",
        "analysis_revision",
        "evidence_revision",
    ):
        semantic_payload.pop(field)
    semantic_payload["primary_path"] = " -> ".join(semantic_payload["primary_path"])
    semantic_payload["evidence_nodes"] = [
        node for node in semantic_payload["nodes"] if node["role"] == "evidence"
    ]
    semantic_payload["nodes"] = [
        node for node in semantic_payload["nodes"] if node["role"] != "evidence"
    ]
    provider = FakeProvider(semantic_payload)
    planned = SemanticNarrativePlanner(provider).plan(
        document, analysis, evidence, artifact_revision=3
    )

    assert planned.artifact_revision == 3
    assert planned.paper_id == document.paper_id
    call = provider.calls[0]
    assert call["call_id"] == "ppr_minimal:narrative:3"
    assert call["max_output_tokens"] == 8_000
    prompt = call["user_prompt"]
    assert "ANALYSIS\n" in prompt and "EVIDENCE_GRAPH\n" in prompt
    assert "Existing systems are slow." in prompt
    assert '"pages"' not in prompt
    assert '"blocks"' not in prompt
    assert document.source.sha256 not in prompt


def test_narrative_contract_forbids_layout_decisions(project_root):
    *_, valid = _minimal_artifacts(project_root)
    payload = valid.model_dump(mode="json")
    payload["layout"] = {"columns": 3}
    with pytest.raises(ValidationError, match="layout"):
        NarrativePlan.model_validate(payload)
