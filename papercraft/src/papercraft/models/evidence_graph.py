"""Claim-evidence graph and deliberately narrow MVP support assessment."""

from __future__ import annotations

from typing import Literal

from pydantic import Field, PositiveInt, model_validator

from papercraft.models.common import (
    ClaimId,
    EdgeId,
    EvidenceId,
    PaperId,
    Ratio,
    SchemaVersion,
    SourceRefId,
    StrictModel,
    ensure_unique,
)


SufficiencyDimension = Literal[
    "directness",
    "scope_match",
    "baseline_adequacy",
    "ablation_support",
    "robustness",
    "statistical_support",
]


class SufficiencyCheck(StrictModel):
    """One explicit reason why evidence does or does not justify a claim."""

    dimension: SufficiencyDimension
    status: Literal["passed", "failed", "not_applicable", "unknown"]
    rationale: str = Field(min_length=1)
    source_refs: list[SourceRefId] = Field(default_factory=list)


class EvidenceNode(StrictModel):
    evidence_id: EvidenceId
    evidence_type: Literal["experiment_result", "equation", "figure", "table", "text_excerpt"]
    summary: str = Field(min_length=1)
    object_refs: list[str] = Field(min_length=1)
    source_refs: list[SourceRefId] = Field(min_length=1)


class EvidenceEdge(StrictModel):
    edge_id: EdgeId
    from_evidence: EvidenceId
    to_claim: ClaimId
    relation: Literal["supports", "partially_supports", "contextualizes"]
    strength: Ratio
    rationale: str = Field(min_length=1)
    qualifiers: list[str] = Field(default_factory=list)


class ClaimAssessment(StrictModel):
    claim_id: ClaimId
    status: Literal["supported", "partially_supported", "insufficient_evidence"]
    supporting_edges: list[EdgeId]
    sufficiency_checks: list[SufficiencyCheck] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
    rationale: str = Field(min_length=1)


class EvidenceGraph(StrictModel):
    schema_version: SchemaVersion
    artifact_revision: PositiveInt
    paper_id: PaperId
    analysis_revision: PositiveInt
    evidence: list[EvidenceNode] = Field(min_length=1)
    edges: list[EvidenceEdge] = Field(min_length=1)
    claim_assessments: list[ClaimAssessment] = Field(min_length=1)
    orphan_claims: list[ClaimId] = Field(default_factory=list)
    orphan_evidence: list[EvidenceId] = Field(default_factory=list)

    @model_validator(mode="after")
    def graph_integrity(self) -> "EvidenceGraph":
        ensure_unique((item.evidence_id for item in self.evidence), "evidence ID")
        ensure_unique((item.edge_id for item in self.edges), "evidence edge ID")
        ensure_unique((item.claim_id for item in self.claim_assessments), "claim assessment")

        evidence_ids = {item.evidence_id for item in self.evidence}
        edge_ids = {item.edge_id for item in self.edges}
        for edge in self.edges:
            if edge.from_evidence not in evidence_ids:
                raise ValueError(f"edge {edge.edge_id} references unknown evidence")
        for assessment in self.claim_assessments:
            ensure_unique(
                (check.dimension for check in assessment.sufficiency_checks),
                f"sufficiency dimension for {assessment.claim_id}",
            )
            missing = set(assessment.supporting_edges) - edge_ids
            if missing:
                raise ValueError(f"assessment {assessment.claim_id} references unknown edges: {sorted(missing)}")
        if set(self.orphan_evidence) - evidence_ids:
            raise ValueError("orphan_evidence contains unknown evidence IDs")
        return self
