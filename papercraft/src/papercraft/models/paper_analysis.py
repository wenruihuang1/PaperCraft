"""Structured paper logic used by evidence alignment and poster planning."""

from __future__ import annotations

from typing import Literal

from pydantic import Field, PositiveInt, model_validator

from papercraft.models.common import (
    ClaimId,
    ConceptId,
    EquationId,
    ExperimentId,
    MethodId,
    PaperId,
    ResultId,
    SchemaVersion,
    SourceEquationId,
    SourceRefId,
    StrictModel,
    ensure_unique,
)


Importance = Literal["critical", "high", "medium", "low"]


class Concept(StrictModel):
    concept_id: ConceptId
    concept_type: Literal["problem", "motivation", "key_insight", "conclusion"]
    statement: str = Field(min_length=1)
    importance: Importance
    source_refs: list[SourceRefId] = Field(min_length=1)


class ProblemNarrative(StrictModel):
    """Reader-facing problem frame, separated from a section summary."""

    concept_ref: ConceptId
    context: str = Field(min_length=1)
    conventional_assumption: str = Field(min_length=1)
    failure_mechanism: str = Field(min_length=1)
    consequence: str = Field(min_length=1)
    source_refs: list[SourceRefId] = Field(min_length=1)


class MotivationNarrative(StrictModel):
    concept_ref: ConceptId
    observation: str = Field(min_length=1)
    limitation: str = Field(min_length=1)
    design_requirement: str = Field(min_length=1)
    source_refs: list[SourceRefId] = Field(min_length=1)


class InsightNarrative(StrictModel):
    concept_ref: ConceptId
    principle: str = Field(min_length=1)
    operationalization: str = Field(min_length=1)
    expected_effect: str = Field(min_length=1)
    source_refs: list[SourceRefId] = Field(min_length=1)


class NarrativeFrame(StrictModel):
    problem: ProblemNarrative
    motivation: MotivationNarrative
    insight: InsightNarrative


class Claim(StrictModel):
    claim_id: ClaimId
    statement: str = Field(min_length=1)
    claim_type: Literal["main", "supporting"]
    scope: str = Field(min_length=1)
    qualifiers: list[str] = Field(default_factory=list)
    importance: Importance
    source_refs: list[SourceRefId] = Field(min_length=1)


class MethodStep(StrictModel):
    index: PositiveInt
    description: str = Field(min_length=1)
    source_refs: list[SourceRefId] = Field(min_length=1)


class Method(StrictModel):
    method_id: MethodId
    name: str = Field(min_length=1)
    purpose: str = Field(min_length=1)
    inputs: list[str]
    outputs: list[str]
    steps: list[MethodStep] = Field(min_length=1)
    assumptions: list[str] = Field(default_factory=list)
    equation_refs: list[EquationId] = Field(default_factory=list)
    claim_refs: list[ClaimId] = Field(default_factory=list)
    source_refs: list[SourceRefId] = Field(min_length=1)


class EquationVariable(StrictModel):
    symbol: str = Field(min_length=1)
    meaning: str = Field(min_length=1)
    unit: str | None = None
    domain: str | None = None


class AnalysisEquation(StrictModel):
    equation_id: EquationId
    source_equation_id: SourceEquationId
    label: str | None = None
    latex_original: str = Field(min_length=1)
    semantic_role: Literal[
        "definition",
        "objective",
        "constraint",
        "update_rule",
        "metric",
        "other",
    ]
    variables: list[EquationVariable]
    computation_steps: list[str]
    method_refs: list[MethodId] = Field(default_factory=list)
    experiment_refs: list[ExperimentId] = Field(default_factory=list)
    source_refs: list[SourceRefId] = Field(min_length=1)


class ExperimentResult(StrictModel):
    result_id: ResultId
    metric: str = Field(min_length=1)
    value: str = Field(min_length=1)
    comparison: str | None = None
    source_refs: list[SourceRefId] = Field(min_length=1)


class Experiment(StrictModel):
    experiment_id: ExperimentId
    question: str = Field(min_length=1)
    setup: str = Field(min_length=1)
    datasets: list[str]
    metrics: list[str]
    baselines: list[str]
    results: list[ExperimentResult] = Field(min_length=1)
    limitations: list[str] = Field(default_factory=list)
    claim_refs: list[ClaimId] = Field(default_factory=list)
    source_refs: list[SourceRefId] = Field(min_length=1)


class UnderstandingStep(StrictModel):
    step_id: str = Field(pattern=r"^step_[a-z0-9_]+$")
    role: Literal["problem", "motivation", "key_insight", "method", "evidence", "conclusion"]
    object_refs: list[str] = Field(min_length=1)
    transition: str | None = None


class AnalysisMetadata(StrictModel):
    title: str = Field(min_length=1)
    authors: list[str]
    language: Literal["en"]


class PaperAnalysis(StrictModel):
    schema_version: SchemaVersion
    artifact_revision: PositiveInt
    paper_id: PaperId
    source_revision: PositiveInt
    metadata: AnalysisMetadata
    concepts: list[Concept] = Field(min_length=1)
    claims: list[Claim] = Field(min_length=1)
    methods: list[Method] = Field(min_length=1)
    equations: list[AnalysisEquation] = Field(default_factory=list)
    experiments: list[Experiment] = Field(min_length=1)
    narrative_frame: NarrativeFrame | None = None
    understanding_path: list[UnderstandingStep] = Field(min_length=1)
    analysis_warnings: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def unique_ids(self) -> "PaperAnalysis":
        ensure_unique((item.concept_id for item in self.concepts), "concept ID")
        ensure_unique((item.claim_id for item in self.claims), "claim ID")
        ensure_unique((item.method_id for item in self.methods), "method ID")
        ensure_unique((item.equation_id for item in self.equations), "equation ID")
        ensure_unique((item.experiment_id for item in self.experiments), "experiment ID")
        ensure_unique(
            (result.result_id for experiment in self.experiments for result in experiment.results),
            "result ID",
        )
        ensure_unique((item.step_id for item in self.understanding_path), "understanding step ID")
        concept_types = {item.concept_type for item in self.concepts}
        missing = {"problem", "motivation"} - concept_types
        if missing:
            raise ValueError(
                "paper analysis requires concept coverage for: " + ", ".join(sorted(missing))
            )
        if self.schema_version == "1.2.0" and self.narrative_frame is None:
            raise ValueError("paper analysis 1.2 requires a narrative_frame")
        if self.narrative_frame is not None:
            concept_ids = {item.concept_id for item in self.concepts}
            narrative_refs = {
                self.narrative_frame.problem.concept_ref,
                self.narrative_frame.motivation.concept_ref,
                self.narrative_frame.insight.concept_ref,
            }
            if not narrative_refs <= concept_ids:
                raise ValueError("narrative_frame references an unknown concept")
        return self
