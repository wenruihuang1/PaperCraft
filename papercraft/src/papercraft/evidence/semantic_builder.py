"""Source-grounded evidence graph generation."""

from __future__ import annotations

import json
import os

from pydantic import Field, PositiveInt

from papercraft.models import DocumentIR, EvidenceGraph, PaperAnalysis
from papercraft.models.common import PaperId, SchemaVersion, StrictModel
from papercraft.models.evidence_graph import ClaimAssessment, EvidenceEdge, EvidenceNode
from papercraft.providers import StructuredProvider


EVIDENCE_PROMPT = """Build a claim-evidence graph from the supplied validated analysis and
source packet. Assess every claim exactly once using only supported, partially_supported, or
insufficient_evidence. Evidence must reference existing semantic object IDs and source_ref IDs.
For each claim explicitly check directness, scope match, baseline adequacy, ablation support,
robustness, and statistical support. Use not_applicable or unknown instead of inventing evidence.
Broad claims require broad evidence; distinguish pruning-only results from distillation results.
Keep the graph poster-sized: create at most two evidence nodes and two supporting edges per claim,
reuse an evidence node across claims when appropriate, keep summaries under 30 words, rationales
under 25 words, qualifiers under 15 words, and cite at most three strongest source_ref IDs per
object. Return exactly one ClaimAssessment per claim and exactly one SufficiencyCheck for each of
the six required dimensions. Completeness of claim assessments is more important than adding
extra evidence nodes. Before finishing, verify that the output contains a non-empty
claim_assessments array with exactly one assessment for every claim_id in ANALYSIS. Do not return
an empty object or omit claim_assessments, even when a claim has insufficient evidence. The
overall assessment status may be supported, partially_supported, or insufficient_evidence, but
each individual sufficiency_check.status must be only passed, failed, not_applicable, or unknown;
never use an overall assessment status inside a sufficiency check."""


class EvidenceGraphDraft(StrictModel):
    """Provider transport shape before deterministic ID normalization."""

    schema_version: SchemaVersion
    artifact_revision: PositiveInt
    paper_id: PaperId
    analysis_revision: PositiveInt
    evidence: list[EvidenceNode] = Field(min_length=1)
    edges: list[EvidenceEdge] = Field(min_length=1)
    claim_assessments: list[ClaimAssessment] = Field(min_length=1)
    orphan_claims: list[str] = Field(default_factory=list)
    orphan_evidence: list[str] = Field(default_factory=list)


class SemanticEvidenceBuilder:
    def __init__(self, provider: StructuredProvider) -> None:
        self.provider = provider

    def build(
        self,
        document_ir: DocumentIR,
        analysis: PaperAnalysis,
        *,
        artifact_revision: int = 1,
    ) -> EvidenceGraph:
        cited_source_ids: set[str] = set()
        for collection in (
            analysis.concepts,
            analysis.claims,
            analysis.methods,
            analysis.equations,
            analysis.experiments,
        ):
            for item in collection:
                cited_source_ids.update(getattr(item, "source_refs", []) or [])
                for child_name in ("steps", "results"):
                    for child in getattr(item, child_name, []) or []:
                        cited_source_ids.update(
                            getattr(child, "source_refs", []) or []
                        )
        sources = "\n".join(
            f"[{ref.source_ref_id} | page {ref.locator.page} | {ref.source_type}] {ref.quote}"
            for ref in document_ir.source_refs
            if ref.source_ref_id in cited_source_ids
        )
        result = self.provider.generate(
            call_id=f"{document_ir.paper_id}:evidence:{artifact_revision}",
            system_prompt=EVIDENCE_PROMPT,
            user_prompt=(
                "ANALYSIS\n"
                + json.dumps(analysis.model_dump(mode="json"), ensure_ascii=False)
                + "\n\nALLOWED_SOURCE_REF_IDS\n"
                + "\n".join(sorted(cited_source_ids))
                + "\n\nSOURCES\n"
                + sources
            ),
            output_model=EvidenceGraphDraft,
            max_output_tokens=int(os.getenv("PAPERCRAFT_EVIDENCE_MAX_OUTPUT_TOKENS", "12_000")),
            reasoning_effort=os.getenv("PAPERCRAFT_EVIDENCE_REASONING_EFFORT", "low"),
            strict_output=False,
        ).value
        # Revisions and identity are pipeline-owned metadata, not semantic
        # judgments. Always stamp the current values after validating Claude's
        # structured graph so a stale copied revision cannot invalidate an
        # otherwise usable result.
        payload = result.model_dump(mode="json")
        payload.update(
            {
                "schema_version": "1.2.0",
                "artifact_revision": artifact_revision,
                "paper_id": document_ir.paper_id,
                "analysis_revision": analysis.artifact_revision,
            }
        )
        payload["evidence"] = _dedupe(payload["evidence"], "evidence_id")
        payload["edges"] = _dedupe(payload["edges"], "edge_id")
        payload["claim_assessments"] = _dedupe(
            payload["claim_assessments"], "claim_id"
        )
        _complete_sufficiency_checks(payload)
        return EvidenceGraph.model_validate(payload)


def _dedupe(items: list[dict], id_field: str) -> list[dict]:
    """Keep the first provider object for each stable ID, preserving order."""

    seen: set[str] = set()
    result: list[dict] = []
    for item in items:
        object_id = item[id_field]
        if object_id in seen:
            continue
        seen.add(object_id)
        result.append(item)
    return result


def _complete_sufficiency_checks(payload: dict) -> None:
    """Preserve uncertainty while making the six-dimension contract total.

    Tool schemas cannot require one item for every enum member, and providers
    occasionally return an otherwise valid assessment with an empty or partial
    list. Missing dimensions are not silently marked as passed: they are filled
    as ``unknown`` and grounded in the assessment's supporting evidence.
    """

    dimensions = (
        "directness",
        "scope_match",
        "baseline_adequacy",
        "ablation_support",
        "robustness",
        "statistical_support",
    )
    evidence_by_id = {
        item["evidence_id"]: item for item in payload.get("evidence", [])
    }
    edges_by_id = {item["edge_id"]: item for item in payload.get("edges", [])}
    for assessment in payload.get("claim_assessments", []):
        checks = assessment.setdefault("sufficiency_checks", [])
        present = {item["dimension"] for item in checks}
        source_refs: list[str] = []
        for edge_id in assessment.get("supporting_edges", []):
            edge = edges_by_id.get(edge_id)
            if edge is None:
                continue
            node = evidence_by_id.get(edge["from_evidence"])
            if node is None:
                continue
            for source_ref in node.get("source_refs", []):
                if source_ref not in source_refs:
                    source_refs.append(source_ref)
        for dimension in dimensions:
            if dimension not in present:
                checks.append(
                    {
                        "dimension": dimension,
                        "status": "unknown",
                        "rationale": "The semantic provider did not explicitly assess this dimension.",
                        "source_refs": source_refs[:3],
                    }
                )
