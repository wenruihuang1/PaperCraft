"""Provider-neutral schema for an independent semantic audit."""

from __future__ import annotations

import json
from typing import Literal

from pydantic import Field

from papercraft.models import DocumentIR, EvidenceGraph, PaperAnalysis
from papercraft.models.common import StrictModel
from papercraft.providers import StructuredProvider


class SemanticAuditFinding(StrictModel):
    checker: Literal["content_completeness", "evidence_sufficiency", "formula_accuracy"]
    severity: Literal["warning", "error"]
    target_artifact: Literal["paper_analysis", "evidence_graph"]
    target_id: str = Field(min_length=1)
    message: str = Field(min_length=1)
    source_refs: list[str] = Field(default_factory=list)
    repair_instruction: str = Field(min_length=1)


class SemanticAudit(StrictModel):
    findings: list[SemanticAuditFinding] = Field(default_factory=list)


SEMANTIC_AUDIT_PROMPT = """Act as an independent, skeptical research-paper reviewer.
Inspect content completeness, evidence sufficiency, and formula accuracy. Report only
actionable findings. Never invent sources. Every cited source_ref must occur in the supplied
source list. A broad claim needs evidence matching its scope. Separate pruning-only evidence
from post-distillation evidence. Numerical contradictions are errors. Formula symbols must
remain faithful to the source. Return a constrained structured audit, not prose."""


def run_semantic_audit(
    provider: StructuredProvider,
    document_ir: DocumentIR,
    analysis: PaperAnalysis,
    evidence: EvidenceGraph,
    *,
    round_number: int = 1,
) -> SemanticAudit:
    source_ids = {item.source_ref_id for item in document_ir.source_refs}
    cited_ids = {
        ref
        for collection in (
            analysis.concepts,
            analysis.claims,
            analysis.methods,
            analysis.equations,
            analysis.experiments,
            evidence.evidence,
        )
        for item in collection
        for ref in item.source_refs
    }
    sources = "\n".join(
        f"[{item.source_ref_id} | p.{item.locator.page}] {item.quote}"
        for item in document_ir.source_refs
        if item.source_ref_id in cited_ids
    )
    result = provider.generate(
        call_id=(
            f"{document_ir.paper_id}:semantic-audit:"
            f"{analysis.artifact_revision}:{round_number}"
        ),
        system_prompt=SEMANTIC_AUDIT_PROMPT,
        user_prompt=(
            "PAPER_ANALYSIS\n"
            + json.dumps(analysis.model_dump(mode="json"), ensure_ascii=False)
            + "\n\nEVIDENCE_GRAPH\n"
            + json.dumps(evidence.model_dump(mode="json"), ensure_ascii=False)
            + "\n\nSOURCES\n"
            + sources
        ),
        output_model=SemanticAudit,
        max_output_tokens=3_500,
    ).value
    invalid = sorted(
        {
            source_ref
            for finding in result.findings
            for source_ref in finding.source_refs
            if source_ref not in source_ids
        }
    )
    if invalid:
        raise ValueError(f"semantic audit cited unknown source refs: {invalid}")
    return result
