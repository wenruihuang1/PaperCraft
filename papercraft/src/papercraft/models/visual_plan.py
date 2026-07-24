"""Constrained visual direction between NarrativePlan and PosterPlan."""

from __future__ import annotations

from typing import Literal

from pydantic import Field, PositiveInt, model_validator

from papercraft.models.common import ComponentId, PaperId, SchemaVersion, StrictModel, ensure_unique
from papercraft.models.narrative_plan import NarrativeNodeId


VisualArchetype = Literal[
    "pipeline_story",
    "cause_intervention_effect",
    "mechanism_explainer",
    "benchmark_matrix",
    "case_gallery",
    "dataset_landscape",
    "theory_derivation",
    "decision_loop",
    "agent_workflow",
    "system_architecture",
    "taxonomy_map",
    "balanced_story",
]


class VisualPlan(StrictModel):
    """A renderer-safe visual interpretation with no free-form layout geometry."""

    schema_version: SchemaVersion
    artifact_revision: PositiveInt
    paper_id: PaperId
    narrative_revision: PositiveInt
    baseline_poster_revision: PositiveInt
    visual_archetype: VisualArchetype
    component_sequence: list[ComponentId] = Field(min_length=1)
    primary_node_refs: list[NarrativeNodeId] = Field(min_length=5, max_length=9)
    hero_node_refs: list[NarrativeNodeId] = Field(min_length=1, max_length=3)
    status: Literal["applied", "fallback"] = "applied"
    fallback_reason: str | None = None

    @model_validator(mode="after")
    def integrity(self) -> "VisualPlan":
        ensure_unique(self.component_sequence, "visual component sequence")
        ensure_unique(self.primary_node_refs, "visual primary node reference")
        ensure_unique(self.hero_node_refs, "visual hero node reference")
        if self.status == "applied" and self.fallback_reason is not None:
            raise ValueError("an applied visual plan cannot have a fallback reason")
        if self.status == "fallback" and not self.fallback_reason:
            raise ValueError("a fallback visual plan requires a fallback reason")
        if not set(self.hero_node_refs) <= set(self.primary_node_refs):
            raise ValueError("visual hero nodes must appear in the primary path")
        return self
