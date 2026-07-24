"""Typed, object-local semantic repairs requested from the primary provider."""

from __future__ import annotations

import hashlib
import json
from typing import Annotated, Literal, Union

from pydantic import Field

from papercraft.models import DocumentIR, EvidenceGraph, PaperAnalysis
from papercraft.models.common import StrictModel
from papercraft.models.evidence_graph import ClaimAssessment, EvidenceEdge, EvidenceNode
from papercraft.models.paper_analysis import AnalysisEquation, Claim, Concept, Experiment, Method
from papercraft.providers import StructuredProvider
from papercraft.review.semantic_audit import SemanticAuditFinding


class ReplaceConcept(StrictModel):
    operation: Literal["replace_concept"]
    target_id: str
    replacement: Concept


class ReplaceClaim(StrictModel):
    operation: Literal["replace_claim"]
    target_id: str
    replacement: Claim


class ReplaceMethod(StrictModel):
    operation: Literal["replace_method"]
    target_id: str
    replacement: Method


class ReplaceEquation(StrictModel):
    operation: Literal["replace_equation"]
    target_id: str
    replacement: AnalysisEquation


class ReplaceExperiment(StrictModel):
    operation: Literal["replace_experiment"]
    target_id: str
    replacement: Experiment


class ReplaceEvidenceNode(StrictModel):
    operation: Literal["replace_evidence_node"]
    target_id: str
    replacement: EvidenceNode


class ReplaceEvidenceEdge(StrictModel):
    operation: Literal["replace_evidence_edge"]
    target_id: str
    replacement: EvidenceEdge


class ReplaceClaimAssessment(StrictModel):
    operation: Literal["replace_claim_assessment"]
    target_id: str
    replacement: ClaimAssessment


SemanticReplacement = Annotated[
    Union[
        ReplaceConcept,
        ReplaceClaim,
        ReplaceMethod,
        ReplaceEquation,
        ReplaceExperiment,
        ReplaceEvidenceNode,
        ReplaceEvidenceEdge,
        ReplaceClaimAssessment,
    ],
    Field(discriminator="operation"),
]


class SemanticRepairBatch(StrictModel):
    replacements: list[SemanticReplacement] = Field(default_factory=list)


REPAIR_PROMPT = """Repair only the objects explicitly named by the independent audit.
Return typed full-object replacements, never a regenerated artifact. Keep every stable target ID
unchanged. Copy source_ref IDs exactly from the supplied sources. Preserve correct qualifiers,
formula symbols, experiment scope, and all unrelated objects. For a nested result finding,
replace its parent Experiment. Do not return replacements for warning-only findings."""


def request_semantic_repairs(
    provider: StructuredProvider,
    document_ir: DocumentIR,
    analysis: PaperAnalysis,
    evidence: EvidenceGraph,
    findings: list[SemanticAuditFinding],
    *,
    round_number: int,
) -> SemanticRepairBatch:
    errors = [item for item in findings if item.severity == "error"]
    sources = "\n".join(
        f"[{item.source_ref_id} | p.{item.locator.page}] {item.quote}"
        for item in document_ir.source_refs
    )
    return provider.generate(
        call_id=(
            f"{document_ir.paper_id}:semantic-repair:"
            f"{analysis.artifact_revision}:{round_number}"
        ),
        system_prompt=REPAIR_PROMPT,
        user_prompt=(
            "AUDIT ERRORS\n"
            + json.dumps([item.model_dump(mode="json") for item in errors], ensure_ascii=False)
            + "\n\nPAPER_ANALYSIS\n"
            + json.dumps(analysis.model_dump(mode="json"), ensure_ascii=False)
            + "\n\nEVIDENCE_GRAPH\n"
            + json.dumps(evidence.model_dump(mode="json"), ensure_ascii=False)
            + "\n\nSOURCES\n"
            + sources
        ),
        output_model=SemanticRepairBatch,
        max_output_tokens=3_500,
        strict_output=False,
    ).value


def apply_semantic_repairs(
    analysis: PaperAnalysis,
    evidence: EvidenceGraph,
    batch: SemanticRepairBatch,
) -> tuple[PaperAnalysis, EvidenceGraph]:
    analysis_payload = analysis.model_dump(mode="json")
    evidence_payload = evidence.model_dump(mode="json")
    before = semantic_object_hashes(analysis, evidence)
    targeted: set[str] = set()
    analysis_changed = False
    evidence_changed = False
    routes = {
        "replace_concept": (analysis_payload["concepts"], "concept_id", True),
        "replace_claim": (analysis_payload["claims"], "claim_id", True),
        "replace_method": (analysis_payload["methods"], "method_id", True),
        "replace_equation": (analysis_payload["equations"], "equation_id", True),
        "replace_experiment": (analysis_payload["experiments"], "experiment_id", True),
        "replace_evidence_node": (evidence_payload["evidence"], "evidence_id", False),
        "replace_evidence_edge": (evidence_payload["edges"], "edge_id", False),
        "replace_claim_assessment": (
            evidence_payload["claim_assessments"],
            "claim_id",
            False,
        ),
    }
    for replacement in batch.replacements:
        collection, id_field, is_analysis = routes[replacement.operation]
        replacement_payload = replacement.replacement.model_dump(mode="json")
        if replacement_payload[id_field] != replacement.target_id:
            raise ValueError(
                f"semantic replacement changed stable ID {replacement.target_id}"
            )
        matches = [index for index, item in enumerate(collection) if item[id_field] == replacement.target_id]
        if len(matches) != 1:
            raise ValueError(f"semantic repair target does not resolve exactly once: {replacement.target_id}")
        collection[matches[0]] = replacement_payload
        targeted.add(
            f"{replacement.replacement.__class__.__name__}:{replacement.target_id}"
        )
        analysis_changed = analysis_changed or is_analysis
        evidence_changed = evidence_changed or not is_analysis

    if analysis_changed:
        analysis_payload["artifact_revision"] = analysis.artifact_revision + 1
    repaired_analysis = PaperAnalysis.model_validate(analysis_payload)
    if analysis_changed or evidence_changed:
        evidence_payload["artifact_revision"] = evidence.artifact_revision + 1
    evidence_payload["analysis_revision"] = repaired_analysis.artifact_revision
    repaired_evidence = EvidenceGraph.model_validate(evidence_payload)
    after = semantic_object_hashes(repaired_analysis, repaired_evidence)
    for object_id, digest in before.items():
        if object_id not in targeted and after.get(object_id) != digest:
            raise ValueError(f"semantic repair changed untouched object {object_id}")
    return repaired_analysis, repaired_evidence


def semantic_object_hashes(
    analysis: PaperAnalysis, evidence: EvidenceGraph
) -> dict[str, str]:
    objects = (
        list(analysis.concepts)
        + list(analysis.claims)
        + list(analysis.methods)
        + list(analysis.equations)
        + list(analysis.experiments)
        + list(evidence.evidence)
        + list(evidence.edges)
        + list(evidence.claim_assessments)
    )
    return {
        f"{item.__class__.__name__}:{_semantic_id(item)}": hashlib.sha256(
            json.dumps(item.model_dump(mode="json"), sort_keys=True, ensure_ascii=False).encode()
        ).hexdigest()
        for item in objects
    }


def _semantic_id(item) -> str:
    for field in (
        "concept_id",
        "claim_id",
        "method_id",
        "equation_id",
        "experiment_id",
        "evidence_id",
        "edge_id",
    ):
        value = getattr(item, field, None)
        if value:
            return value
    raise ValueError("semantic object has no stable ID")
