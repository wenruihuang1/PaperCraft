"""Conservative evidence graph for the extractive offline fallback.

This is deliberately less ambitious than semantic review.  It connects every
extractive claim to the exact source passage selected by the heuristic
analyzer, marks the support as partial, and leaves dimensions that require
scientific judgment unknown.
"""

from __future__ import annotations

from papercraft.models import DocumentIR, EvidenceGraph, PaperAnalysis
from papercraft.models.evidence_graph import (
    ClaimAssessment,
    EvidenceEdge,
    EvidenceNode,
    SufficiencyCheck,
)


class OfflineEvidenceBuilder:
    """Build a total, source-addressable graph without an LLM."""

    def build(
        self,
        document_ir: DocumentIR,
        analysis: PaperAnalysis,
        *,
        artifact_revision: int = 1,
    ) -> EvidenceGraph:
        evidence: list[EvidenceNode] = []
        edges: list[EvidenceEdge] = []
        assessments: list[ClaimAssessment] = []
        for index, claim in enumerate(analysis.claims, start=1):
            evidence_id = f"ev_offline_{index:02d}"
            edge_id = f"edge_offline_{index:02d}"
            evidence.append(
                EvidenceNode(
                    evidence_id=evidence_id,
                    evidence_type="text_excerpt",
                    summary="Extractive source passage selected for the reported claim.",
                    object_refs=[claim.claim_id],
                    source_refs=claim.source_refs,
                )
            )
            edges.append(
                EvidenceEdge(
                    edge_id=edge_id,
                    from_evidence=evidence_id,
                    to_claim=claim.claim_id,
                    relation="partially_supports",
                    strength=0.55,
                    rationale="The wording is source-extractive; broader scientific support was not semantically audited.",
                    qualifiers=["offline extractive fallback"],
                )
            )
            assessments.append(
                ClaimAssessment(
                    claim_id=claim.claim_id,
                    status="partially_supported",
                    supporting_edges=[edge_id],
                    sufficiency_checks=[
                        SufficiencyCheck(
                            dimension=dimension,
                            status="unknown",
                            rationale="This dimension requires semantic review beyond the offline fallback.",
                            source_refs=claim.source_refs,
                        )
                        for dimension in (
                            "directness",
                            "scope_match",
                            "baseline_adequacy",
                            "ablation_support",
                            "robustness",
                            "statistical_support",
                        )
                    ],
                    limitations=[
                        "No LLM semantic audit was available; verify the claim against the linked source passage."
                    ],
                    rationale="The source passage is preserved, but support sufficiency remains unverified.",
                )
            )
        return EvidenceGraph(
            schema_version="1.2.0",
            artifact_revision=artifact_revision,
            paper_id=document_ir.paper_id,
            analysis_revision=analysis.artifact_revision,
            evidence=evidence,
            edges=edges,
            claim_assessments=assessments,
        )
