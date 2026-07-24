"""Structured output for the three MVP reviewers and targeted repair routing."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import Field, PositiveInt, model_validator

from papercraft.models.common import (
    ComponentId,
    IssueId,
    PaperId,
    PatchId,
    ReviewId,
    SchemaVersion,
    StrictModel,
    ensure_unique,
)


Checker = Literal[
    "source_consistency",
    "content_completeness",
    "evidence_sufficiency",
    "formula_accuracy",
    "global_layout",
    "local_overflow",
]
TargetArtifact = Literal[
    "document_ir",
    "paper_analysis",
    "evidence_graph",
    "poster_plan",
    "html_render",
    "pdf_render",
]


class InputRevisions(StrictModel):
    document_ir: PositiveInt
    paper_analysis: PositiveInt
    evidence_graph: PositiveInt
    poster_plan: PositiveInt
    html_render: PositiveInt | None = None
    pdf_render: PositiveInt | None = None


class CheckerSummary(StrictModel):
    checker: Checker
    status: Literal["passed", "failed"]
    issue_count: int = Field(ge=0)


class IssueTarget(StrictModel):
    artifact: TargetArtifact
    target_id: str | None = None
    field: str | None = None


class SuggestedPatch(StrictModel):
    patch_id: PatchId
    operation: Literal[
        "restore_source_value",
        "resize",
        "shorten_summary",
        "shorten_narrative",
        "shorten_title",
        "collapse_details",
        "reorder",
        "increase_gap",
        "adjust_chart_labels",
        "adjust_semantic_crop",
        "replace_content",
        "qualify_claim",
        "repair_formula",
        "relink_evidence",
    ]
    target_id: str
    parameters: dict[str, Any] = Field(default_factory=dict)
    expected_revision: PositiveInt


class ReviewIssue(StrictModel):
    issue_id: IssueId
    checker: Checker
    code: Literal[
        "MISSING_SOURCE_REF",
        "UNRESOLVABLE_SOURCE_REF",
        "QUOTE_MISMATCH",
        "NUMERIC_MISMATCH",
        "FORMULA_SOURCE_MISMATCH",
        "EVIDENCE_TARGET_MISMATCH",
        "OCCUPANCY_OUT_OF_RANGE",
        "VISUAL_RATIO_OUT_OF_RANGE",
        "FONT_BELOW_MINIMUM",
        "GAP_BELOW_MINIMUM",
        "READING_ORDER_BROKEN",
        "DENSITY_IMBALANCE",
        "TEXT_CLIPPED",
        "ELEMENT_OVERLAP",
        "CANVAS_OVERFLOW",
        "CHART_LABEL_CLIPPED",
        "MISSING_REQUIRED_CONTENT",
        "DUPLICATE_CONTENT",
        "UNSUPPORTED_CLAIM_LANGUAGE",
        "EVIDENCE_SCOPE_MISMATCH",
        "WEAK_BASELINE_COVERAGE",
        "MISSING_ABLATION_SUPPORT",
        "FORMULA_SYMBOL_MISMATCH",
        "FORMULA_VARIABLE_UNDEFINED",
        "FORMULA_METHOD_LINK_MISSING",
        "FORMULA_EXPERIMENT_LINK_MISSING",
        "SOURCE_PREVIEW_MISSING",
        "SOURCE_PREVIEW_INCOMPLETE",
        "FORMULA_RENDER_FAILED",
        "INSPECTOR_CONTENT_CLIPPED",
        "OFFLINE_BOOT_FAILED",
        "NARRATIVE_HEADLINE_CLIPPED",
        "NARRATIVE_BODY_CLIPPED",
        "NARRATIVE_HEADLINE_OVERFLOW",
        "NARRATIVE_BODY_OVERFLOW",
        "POSTER_TITLE_OVERFLOW",
        "COMPONENT_SUMMARY_CLIPPED",
        "NARRATIVE_TEXT_TRUNCATED",
        "TEXT_TRUNCATED",
        "LOW_COMPONENT_UTILIZATION",
        "LARGE_BLANK_REGION",
        "VISUAL_CENTER_IMBALANCE",
        "FORMULA_AREA_MISMATCH",
        "OCCUPANCY_OUT_OF_RANGE",
        "VISUAL_RATIO_OUT_OF_RANGE",
        "READING_ORDER_BROKEN",
        "DENSITY_IMBALANCE",
        "FONT_BELOW_MINIMUM",
        "GAP_BELOW_MINIMUM",
        "TEXT_CLIPPED",
        "ELEMENT_OVERLAP",
        "CANVAS_OVERFLOW",
        "CHART_LABEL_CLIPPED",
    ]
    severity: Literal["warning", "error"]
    target: IssueTarget
    message: str = Field(min_length=1)
    detector_evidence: dict[str, Any] = Field(default_factory=dict)
    suggested_patch: SuggestedPatch | None = None
    status: Literal["open", "resolved", "ignored"]


class RepairBatch(StrictModel):
    operations: list[SuggestedPatch] = Field(default_factory=list)
    affected_component_ids: list[ComponentId] = Field(default_factory=list)
    must_preserve_component_ids: list[ComponentId] = Field(default_factory=list)

    @model_validator(mode="after")
    def disjoint_components(self) -> "RepairBatch":
        ensure_unique(self.affected_component_ids, "affected component ID")
        ensure_unique(self.must_preserve_component_ids, "preserved component ID")
        overlap = set(self.affected_component_ids) & set(self.must_preserve_component_ids)
        if overlap:
            raise ValueError(f"components cannot be both affected and preserved: {sorted(overlap)}")
        return self


class ReviewResult(StrictModel):
    schema_version: SchemaVersion
    artifact_revision: PositiveInt
    review_id: ReviewId
    paper_id: PaperId
    input_revisions: InputRevisions
    status: Literal["passed", "failed"]
    checker_summaries: list[CheckerSummary] = Field(min_length=3, max_length=6)
    issues: list[ReviewIssue] = Field(default_factory=list)
    repair_batch: RepairBatch
    metrics: dict[str, float | int | str | bool | None] = Field(default_factory=dict)

    @model_validator(mode="after")
    def review_integrity(self) -> "ReviewResult":
        ensure_unique((item.checker for item in self.checker_summaries), "checker summary")
        ensure_unique((item.issue_id for item in self.issues), "review issue ID")
        expected_checkers = {
            "source_consistency",
            "global_layout",
            "local_overflow",
        }
        if self.schema_version != "1.0.0":
            expected_checkers |= {
                "content_completeness",
                "evidence_sufficiency",
                "formula_accuracy",
            }
        if {item.checker for item in self.checker_summaries} != expected_checkers:
            raise ValueError(
                "checker_summaries must contain every reviewer required by schema_version"
            )
        for summary in self.checker_summaries:
            checker_issues = [
                issue
                for issue in self.issues
                if issue.checker == summary.checker and issue.status == "open"
            ]
            actual = len(checker_issues)
            if summary.issue_count != actual:
                raise ValueError(f"checker {summary.checker} issue_count does not match issues")
            expected_status = (
                "failed"
                if any(issue.severity == "error" for issue in checker_issues)
                else "passed"
            )
            if summary.status != expected_status:
                raise ValueError(f"checker {summary.checker} status does not match issues")
        expected_status = (
            "failed"
            if any(
                issue.severity == "error" and issue.status == "open"
                for issue in self.issues
            )
            else "passed"
        )
        if self.status != expected_status:
            raise ValueError("review status does not match issues")
        return self
