"""Source-grounded, model-assisted scientific narrative planning."""

from __future__ import annotations

import json
import re
from collections.abc import Iterable
from typing import Any

from pydantic import Field

from papercraft.models import DocumentIR, EvidenceGraph, NarrativePlan, PaperAnalysis
from papercraft.models.common import StrictModel
from papercraft.models.narrative_plan import (
    ClaimCoverage,
    EvidenceNarrativeNode,
    NarrativeArchetype,
    NarrativeEdge,
    OtherNarrativeNode,
)
from papercraft.providers import StructuredProvider
from papercraft.validation import validate_narrative_plan


NARRATIVE_PROMPT = """You are the Narrative Planner in a scientific paper compiler.
Organize the paper's argument; do not summarize its section order and do not make visual,
component, style, or layout decisions. Select exactly one controlled archetype. Build a concise
directed acyclic graph whose primary path contains 5 to 9 nodes and reads as a complete argument
from context/problem/observation/gap to takeaway. The primary path must contain a solution or
explanation node and an evidence node. Use branches only for scientifically useful supporting
material. Before submitting, inspect every adjacent pair A, B in primary_path and verify that
edges contains an explicit directed edge with from_node=A and to_node=B. Do not skip an edge
between primary-path neighbors even when another graph path connects them. In the provider result,
encode primary_path as 5 to 9 node IDs separated only by ` -> `, for example
`nar_problem -> nar_insight -> nar_method -> nar_evidence -> nar_takeaway`.
The saved public artifact converts this string to an ordered array. At least one
ID in primary_path must be the exact node_id of an item returned in evidence_nodes;
merely returning an evidence_nodes item elsewhere in the graph is not sufficient.
Return non-evidence roles in nodes and return role=evidence nodes in the separate evidence_nodes
array. At least one evidence_node is required, and every evidence_node requires evidence_refs.

Choose archetypes by the paper's scientific argument, not by loose word association.
- causal_intervention requires an explicit causal model, confounder, causal mechanism, or named
  intervention in the paper; do not use it merely because a method changes an outcome.
- mechanism centers on explaining why a phenomenon or module works.
- method_pipeline centers on an ordered algorithm or transformation pipeline.
- benchmark_comparison centers on broad comparative performance rather than a new mechanism.
Use the remaining domain-specific archetypes only when their named structure is central, and use
balanced only when no single controlled archetype dominates.

Use only IDs present in ALLOWED_SEMANTIC_OBJECT_IDS, ALLOWED_EVIDENCE_IDS, and
ALLOWED_SOURCE_REF_IDS. Every node must cite at least one semantic object and one source_ref.
Evidence nodes must cite EvidenceGraph evidence IDs. Account for every main claim exactly once as
included or omitted; supporting claims may also be listed. Do not invent facts, mechanisms,
causality, or scope. A partially supported or
insufficient main claim may enter the primary path only with a primary-path limitation or boundary
node that cites the same claim. Phrase nodes and transitions as natural scientific narrative, not as
validation labels. Keep node statements under 55 words and transitions under 30 words. Return only
the typed narrative result."""


class NarrativePlanDraft(StrictModel):
    """Semantic provider shape; pipeline identity and revisions are excluded."""

    archetype: NarrativeArchetype
    thesis: str = Field(min_length=1)
    archetype_rationale: str = Field(min_length=1)
    nodes: list[OtherNarrativeNode] = Field(min_length=4)
    evidence_nodes: list[EvidenceNarrativeNode] = Field(min_length=1)
    edges: list[NarrativeEdge] = Field(min_length=4)
    primary_path: str = Field(min_length=1)
    claim_coverage: list[ClaimCoverage] = Field(default_factory=list)


class SemanticNarrativePlanner:
    """Compile validated semantic artifacts into one canonical narrative graph."""

    def __init__(self, provider: StructuredProvider) -> None:
        self.provider = provider

    def plan(
        self,
        document_ir: DocumentIR,
        analysis: PaperAnalysis,
        evidence: EvidenceGraph,
        *,
        artifact_revision: int = 1,
    ) -> NarrativePlan:
        analysis_payload = analysis.model_dump(mode="json")
        evidence_payload = evidence.model_dump(mode="json")
        cited_source_ids = _referenced_source_ids(
            analysis_payload, evidence_payload
        )
        semantic_ids = _semantic_object_ids(analysis)
        evidence_ids = {item.evidence_id for item in evidence.evidence}
        sources = _source_packet(document_ir, cited_source_ids)

        base_prompt = (
            "ANALYSIS\n"
            + json.dumps(analysis_payload, ensure_ascii=False)
            + "\n\nEVIDENCE_GRAPH\n"
            + json.dumps(evidence_payload, ensure_ascii=False)
            + "\n\nALLOWED_SEMANTIC_OBJECT_IDS\n"
            + "\n".join(sorted(semantic_ids))
            + "\n\nALLOWED_EVIDENCE_IDS\n"
            + "\n".join(sorted(evidence_ids))
            + "\n\nALLOWED_SOURCE_REF_IDS\n"
            + "\n".join(sorted(cited_source_ids))
            + "\n\nSOURCES\n"
            + sources
        )
        retry_context = ""
        for attempt in range(2):
            result = self.provider.generate(
                call_id=(
                    f"{document_ir.paper_id}:narrative:{artifact_revision}"
                    + (":retry" if attempt else "")
                ),
                system_prompt=NARRATIVE_PROMPT,
                user_prompt=base_prompt + retry_context,
                output_model=NarrativePlanDraft,
                max_output_tokens=8_000,
                reasoning_effort="high",
            ).value
            try:
                plan = _compile_narrative_plan(
                    result,
                    document_ir=document_ir,
                    analysis=analysis,
                    evidence=evidence,
                    artifact_revision=artifact_revision,
                )
                validate_narrative_plan(document_ir, analysis, evidence, plan)
                return plan
            except ValueError as exc:
                if attempt:
                    raise
                retry_context = (
                    "\n\nPREVIOUS_ATTEMPT_REJECTED\n"
                    + str(exc)
                    + "\nReturn a corrected complete draft. Ensure primary_path contains "
                    "the exact node_id of an evidence_nodes item and explicit directed "
                    "edges connect every adjacent primary-path pair.\n\nPREVIOUS_DRAFT\n"
                    + result.model_dump_json()
                )
        raise RuntimeError("narrative planner exhausted its bounded retry")


def _compile_narrative_plan(
    result: NarrativePlanDraft,
    *,
    document_ir: DocumentIR,
    analysis: PaperAnalysis,
    evidence: EvidenceGraph,
    artifact_revision: int,
) -> NarrativePlan:
    semantic_payload = result.model_dump(
        mode="json", exclude={"primary_path", "nodes", "evidence_nodes", "edges"}
    )
    primary_path, edges = _ensure_primary_evidence(result)
    return NarrativePlan(
        schema_version="1.0.0",
        artifact_revision=artifact_revision,
        paper_id=document_ir.paper_id,
        analysis_revision=analysis.artifact_revision,
        evidence_revision=evidence.artifact_revision,
        **semantic_payload,
        nodes=[*result.nodes, *result.evidence_nodes],
        edges=edges,
        primary_path=primary_path,
    )


def _ensure_primary_evidence(
    result: NarrativePlanDraft,
) -> tuple[list[str], list[NarrativeEdge]]:
    """Apply one narrow repair when a valid evidence branch misses the main path."""

    path = _parse_primary_path(result.primary_path)
    evidence_ids = {item.node_id for item in result.evidence_nodes}
    if evidence_ids.intersection(path) or len(path) >= 9:
        return path, list(result.edges)
    evidence = next(
        (item for item in result.evidence_nodes if item.importance == "primary"),
        result.evidence_nodes[0],
    )
    insert_at = max(1, len(path) - 1)
    previous = path[insert_at - 1]
    following = path[insert_at]
    path.insert(insert_at, evidence.node_id)
    edges = list(result.edges)
    pairs = {(item.from_node, item.to_node) for item in edges}
    edge_ids = {item.edge_id for item in edges}

    def add_edge(source: str, target: str, relation: str, transition: str) -> None:
        if (source, target) in pairs:
            return
        stem = f"nedge_primary_evidence_{len(edges) + 1}"
        edge_id = stem
        suffix = 2
        while edge_id in edge_ids:
            edge_id = f"{stem}_{suffix}"
            suffix += 1
        edges.append(
            NarrativeEdge(
                edge_id=edge_id,
                from_node=source,
                to_node=target,
                relation=relation,
                transition=transition,
            )
        )
        edge_ids.add(edge_id)
        pairs.add((source, target))

    add_edge(
        previous,
        evidence.node_id,
        "evaluated_by",
        "The reported experiments test the proposed explanation.",
    )
    add_edge(
        evidence.node_id,
        following,
        "supports",
        "The bounded evidence motivates the final takeaway.",
    )
    return path, edges


def _parse_primary_path(value: str) -> list[str]:
    """Convert the compact provider transport into the public typed array."""

    return [item.strip() for item in re.split(r"\s*->\s*", value) if item.strip()]


def _referenced_source_ids(*payloads: Any) -> set[str]:
    result: set[str] = set()

    def visit(value: Any) -> None:
        if isinstance(value, dict):
            for key, child in value.items():
                if key == "source_refs" and isinstance(child, list):
                    result.update(
                        item
                        for item in child
                        if isinstance(item, str) and item.startswith("src_")
                    )
                else:
                    visit(child)
        elif isinstance(value, list):
            for child in value:
                visit(child)

    for payload in payloads:
        visit(payload)
    return result


def _semantic_object_ids(analysis: PaperAnalysis) -> set[str]:
    return {
        *(item.concept_id for item in analysis.concepts),
        *(item.claim_id for item in analysis.claims),
        *(item.method_id for item in analysis.methods),
        *(item.equation_id for item in analysis.equations),
        *(item.experiment_id for item in analysis.experiments),
        *(
            result.result_id
            for experiment in analysis.experiments
            for result in experiment.results
        ),
    }


def _source_packet(document_ir: DocumentIR, source_ids: Iterable[str]) -> str:
    selected = set(source_ids)
    assets = {item.asset_id: item for item in document_ir.assets}
    lines: list[str] = []
    for source_ref in document_ir.source_refs:
        if source_ref.source_ref_id not in selected:
            continue
        caption = ""
        asset_id = source_ref.locator.asset_id
        if asset_id is not None:
            asset_caption = assets[asset_id].caption
            if asset_caption != source_ref.quote:
                caption = f" | caption: {asset_caption}"
        lines.append(
            f"[{source_ref.source_ref_id} | page {source_ref.locator.page} | "
            f"{source_ref.source_type}{caption}] {source_ref.quote}"
        )
    return "\n".join(lines)
