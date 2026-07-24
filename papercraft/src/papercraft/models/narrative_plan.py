"""Audience-neutral scientific narrative graph produced before visual direction."""

from __future__ import annotations

from typing import Annotated, Literal, Union

from pydantic import Field, PositiveInt, StringConstraints, model_validator

from papercraft.models.common import (
    ClaimId,
    EvidenceId,
    PaperId,
    SchemaVersion,
    SourceRefId,
    StrictModel,
    ensure_unique,
)


NarrativeNodeId = Annotated[
    str, StringConstraints(pattern=r"^nar_[a-z0-9_]+$")
]
NarrativeEdgeId = Annotated[
    str, StringConstraints(pattern=r"^nedge_[a-z0-9_]+$")
]

NarrativeArchetype = Literal[
    "causal_intervention",
    "mechanism",
    "method_pipeline",
    "benchmark_comparison",
    "case_based",
    "dataset_characterization",
    "theory_derivation",
    "decision_loop",
    "agent_workflow",
    "system_architecture",
    "taxonomy_survey",
    "balanced",
]

NarrativeRole = Literal[
    "context",
    "problem",
    "observation",
    "gap",
    "claim",
    "insight",
    "intervention",
    "mechanism",
    "method",
    "experiment",
    "evidence",
    "limitation",
    "boundary",
    "takeaway",
]

NarrativeRelation = Literal[
    "frames",
    "motivates",
    "reveals",
    "challenges",
    "causes",
    "addressed_by",
    "operationalizes",
    "enables",
    "explains",
    "evaluated_by",
    "supports",
    "qualifies",
    "limits",
    "leads_to",
]


class NarrativeNodeBase(StrictModel):
    node_id: NarrativeNodeId
    statement: str = Field(min_length=1)
    importance: Literal["primary", "supporting", "context"]
    object_refs: list[str] = Field(min_length=1)
    source_refs: list[SourceRefId] = Field(min_length=1)


class EvidenceNarrativeNode(NarrativeNodeBase):
    role: Literal["evidence"]
    evidence_refs: list[EvidenceId] = Field(min_length=1)


class OtherNarrativeNode(NarrativeNodeBase):
    role: Literal[
        "context",
        "problem",
        "observation",
        "gap",
        "claim",
        "insight",
        "intervention",
        "mechanism",
        "method",
        "experiment",
        "limitation",
        "boundary",
        "takeaway",
    ]
    evidence_refs: list[EvidenceId] = Field(default_factory=list)


NarrativeNode = Annotated[
    Union[EvidenceNarrativeNode, OtherNarrativeNode],
    Field(discriminator="role"),
]


class NarrativeEdge(StrictModel):
    edge_id: NarrativeEdgeId
    from_node: NarrativeNodeId
    to_node: NarrativeNodeId
    relation: NarrativeRelation
    transition: str = Field(min_length=1)


class ClaimCoverage(StrictModel):
    claim_ref: ClaimId
    disposition: Literal["included", "omitted"]
    reason: str = Field(min_length=1)


class NarrativePlan(StrictModel):
    schema_version: SchemaVersion
    artifact_revision: PositiveInt
    paper_id: PaperId
    analysis_revision: PositiveInt
    evidence_revision: PositiveInt
    archetype: NarrativeArchetype
    thesis: str = Field(min_length=1)
    archetype_rationale: str = Field(min_length=1)
    nodes: list[NarrativeNode] = Field(min_length=5)
    edges: list[NarrativeEdge] = Field(min_length=4)
    primary_path: list[NarrativeNodeId] = Field(min_length=5, max_length=9)
    claim_coverage: list[ClaimCoverage] = Field(default_factory=list)

    @model_validator(mode="after")
    def graph_integrity(self) -> "NarrativePlan":
        ensure_unique((item.node_id for item in self.nodes), "narrative node ID")
        ensure_unique((item.edge_id for item in self.edges), "narrative edge ID")
        ensure_unique(self.primary_path, "primary path node ID")
        ensure_unique(
            (item.claim_ref for item in self.claim_coverage),
            "narrative claim coverage",
        )

        node_ids = {item.node_id for item in self.nodes}
        for edge in self.edges:
            if edge.from_node not in node_ids or edge.to_node not in node_ids:
                raise ValueError(
                    f"narrative edge {edge.edge_id} references an unknown node"
                )
            if edge.from_node == edge.to_node:
                raise ValueError(f"narrative edge {edge.edge_id} is a self-loop")
        if set(self.primary_path) - node_ids:
            raise ValueError("primary_path references an unknown narrative node")

        directed_edges = {(item.from_node, item.to_node) for item in self.edges}
        for left, right in zip(self.primary_path, self.primary_path[1:]):
            if (left, right) not in directed_edges:
                raise ValueError(
                    f"primary_path has no directed edge from {left} to {right}"
                )

        nodes_by_id = {item.node_id: item for item in self.nodes}
        first_role = nodes_by_id[self.primary_path[0]].role
        if first_role not in {"context", "problem", "observation", "gap"}:
            raise ValueError("primary_path must start with context, problem, observation, or gap")
        if nodes_by_id[self.primary_path[-1]].role != "takeaway":
            raise ValueError("primary_path must end with a takeaway")
        path_roles = {nodes_by_id[node_id].role for node_id in self.primary_path}
        if not path_roles & {"insight", "intervention", "mechanism", "method"}:
            raise ValueError("primary_path requires a solution or explanation node")
        if "evidence" not in path_roles:
            raise ValueError("primary_path requires an evidence node")

        self._validate_connected(node_ids)
        self._validate_acyclic(node_ids)
        return self

    def _validate_connected(self, node_ids: set[str]) -> None:
        undirected: dict[str, set[str]] = {node_id: set() for node_id in node_ids}
        for edge in self.edges:
            undirected[edge.from_node].add(edge.to_node)
            undirected[edge.to_node].add(edge.from_node)
        visited: set[str] = set()
        pending = [next(iter(node_ids))]
        while pending:
            node_id = pending.pop()
            if node_id in visited:
                continue
            visited.add(node_id)
            pending.extend(undirected[node_id] - visited)
        if visited != node_ids:
            raise ValueError("narrative graph must be weakly connected")

    def _validate_acyclic(self, node_ids: set[str]) -> None:
        outgoing: dict[str, list[str]] = {node_id: [] for node_id in node_ids}
        indegree = {node_id: 0 for node_id in node_ids}
        for edge in self.edges:
            outgoing[edge.from_node].append(edge.to_node)
            indegree[edge.to_node] += 1
        pending = [node_id for node_id, count in indegree.items() if count == 0]
        visited = 0
        while pending:
            node_id = pending.pop()
            visited += 1
            for target in outgoing[node_id]:
                indegree[target] -= 1
                if indegree[target] == 0:
                    pending.append(target)
        if visited != len(node_ids):
            raise ValueError("narrative graph must be acyclic")
