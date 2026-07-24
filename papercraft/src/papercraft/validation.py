"""Cross-artifact reference validation for PaperCraft contracts."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from papercraft.models import (
    DocumentIR,
    EvidenceGraph,
    NarrativePlan,
    PaperAnalysis,
    PosterPlan,
    ReviewResult,
)
from papercraft.models.poster_plan import (
    ClaimEvidenceChainComponent,
    EquationExplorerComponent,
    MethodFlowComponent,
    ResultChartComponent,
    VisualGalleryComponent,
)


@dataclass(frozen=True)
class ReferenceIssue:
    code: str
    path: str
    reference: str
    message: str

    def __str__(self) -> str:
        return f"{self.code} at {self.path}: {self.reference} ({self.message})"


class ArtifactReferenceError(ValueError):
    """Raised with all discovered cross-file reference errors."""

    def __init__(self, issues: Iterable[ReferenceIssue]):
        self.issues = tuple(issues)
        super().__init__("\n".join(str(issue) for issue in self.issues))


def _check_refs(
    issues: list[ReferenceIssue],
    refs: Iterable[str],
    valid: set[str],
    path: str,
    code: str,
) -> None:
    for ref in refs:
        if ref not in valid:
            issues.append(
                ReferenceIssue(
                    code=code,
                    path=path,
                    reference=ref,
                    message="reference does not resolve",
                )
            )


def _append_paper_analysis_reference_issues(
    issues: list[ReferenceIssue],
    document_ir: DocumentIR,
    paper_analysis: PaperAnalysis,
) -> None:
    """Append all DocumentIR -> PaperAnalysis provenance and semantic-ref issues."""

    source_refs = {item.source_ref_id for item in document_ir.source_refs}
    source_equations = {item.source_equation_id for item in document_ir.equations}
    claim_ids = {item.claim_id for item in paper_analysis.claims}
    method_ids = {item.method_id for item in paper_analysis.methods}
    equation_ids = {item.equation_id for item in paper_analysis.equations}
    experiment_ids = {item.experiment_id for item in paper_analysis.experiments}
    semantic_ids = (
        {item.concept_id for item in paper_analysis.concepts}
        | claim_ids
        | method_ids
        | equation_ids
        | experiment_ids
        | {
            result.result_id
            for experiment in paper_analysis.experiments
            for result in experiment.results
        }
    )

    for index, concept in enumerate(paper_analysis.concepts):
        _check_refs(
            issues,
            concept.source_refs,
            source_refs,
            f"paper_analysis.concepts[{index}].source_refs",
            "UNRESOLVABLE_SOURCE_REF",
        )
    if paper_analysis.narrative_frame is not None:
        concept_ids = {item.concept_id for item in paper_analysis.concepts}
        for role in ("problem", "motivation", "insight"):
            narrative = getattr(paper_analysis.narrative_frame, role)
            _check_refs(
                issues,
                narrative.source_refs,
                source_refs,
                f"paper_analysis.narrative_frame.{role}.source_refs",
                "UNRESOLVABLE_SOURCE_REF",
            )
            _check_refs(
                issues,
                [narrative.concept_ref],
                concept_ids,
                f"paper_analysis.narrative_frame.{role}.concept_ref",
                "UNKNOWN_CONCEPT_REF",
            )
    for index, claim in enumerate(paper_analysis.claims):
        _check_refs(
            issues,
            claim.source_refs,
            source_refs,
            f"paper_analysis.claims[{index}].source_refs",
            "UNRESOLVABLE_SOURCE_REF",
        )
    for index, method in enumerate(paper_analysis.methods):
        base = f"paper_analysis.methods[{index}]"
        _check_refs(
            issues,
            method.source_refs,
            source_refs,
            f"{base}.source_refs",
            "UNRESOLVABLE_SOURCE_REF",
        )
        _check_refs(
            issues,
            method.equation_refs,
            equation_ids,
            f"{base}.equation_refs",
            "UNKNOWN_EQUATION_REF",
        )
        _check_refs(
            issues,
            method.claim_refs,
            claim_ids,
            f"{base}.claim_refs",
            "UNKNOWN_CLAIM_REF",
        )
        for step_index, step in enumerate(method.steps):
            _check_refs(
                issues,
                step.source_refs,
                source_refs,
                f"{base}.steps[{step_index}].source_refs",
                "UNRESOLVABLE_SOURCE_REF",
            )
    for index, equation in enumerate(paper_analysis.equations):
        base = f"paper_analysis.equations[{index}]"
        _check_refs(
            issues,
            equation.source_refs,
            source_refs,
            f"{base}.source_refs",
            "UNRESOLVABLE_SOURCE_REF",
        )
        _check_refs(
            issues,
            [equation.source_equation_id],
            source_equations,
            f"{base}.source_equation_id",
            "UNKNOWN_SOURCE_EQUATION",
        )
        _check_refs(
            issues,
            equation.method_refs,
            method_ids,
            f"{base}.method_refs",
            "UNKNOWN_METHOD_REF",
        )
        _check_refs(
            issues,
            equation.experiment_refs,
            experiment_ids,
            f"{base}.experiment_refs",
            "UNKNOWN_EXPERIMENT_REF",
        )
        source_equation = next(
            (
                item
                for item in document_ir.equations
                if item.source_equation_id == equation.source_equation_id
            ),
            None,
        )
        if (
            source_equation is not None
            and source_equation.latex is not None
            and equation.latex_original != source_equation.latex
        ):
            issues.append(
                ReferenceIssue(
                    code="FORMULA_SOURCE_MISMATCH",
                    path=f"{base}.latex_original",
                    reference=equation.equation_id,
                    message="latex_original differs from the source equation",
                )
            )
    for index, experiment in enumerate(paper_analysis.experiments):
        base = f"paper_analysis.experiments[{index}]"
        _check_refs(
            issues,
            experiment.source_refs,
            source_refs,
            f"{base}.source_refs",
            "UNRESOLVABLE_SOURCE_REF",
        )
        _check_refs(
            issues,
            experiment.claim_refs,
            claim_ids,
            f"{base}.claim_refs",
            "UNKNOWN_CLAIM_REF",
        )
        for result_index, result in enumerate(experiment.results):
            _check_refs(
                issues,
                result.source_refs,
                source_refs,
                f"{base}.results[{result_index}].source_refs",
                "UNRESOLVABLE_SOURCE_REF",
            )
    for index, step in enumerate(paper_analysis.understanding_path):
        _check_refs(
            issues,
            step.object_refs,
            semantic_ids,
            f"paper_analysis.understanding_path[{index}].object_refs",
            "UNKNOWN_SEMANTIC_REF",
        )


def validate_paper_analysis(
    document_ir: DocumentIR,
    paper_analysis: PaperAnalysis,
) -> None:
    """Validate a PaperAnalysis independently of downstream poster artifacts."""

    issues: list[ReferenceIssue] = []
    if paper_analysis.paper_id != document_ir.paper_id:
        issues.append(
            ReferenceIssue(
                code="PAPER_ID_MISMATCH",
                path="paper_analysis.paper_id",
                reference=paper_analysis.paper_id,
                message=f"expected {document_ir.paper_id}",
            )
        )
    if paper_analysis.source_revision != document_ir.artifact_revision:
        issues.append(
            ReferenceIssue(
                code="REVISION_MISMATCH",
                path="paper_analysis.source_revision",
                reference=str(paper_analysis.source_revision),
                message=f"expected revision {document_ir.artifact_revision}",
            )
        )
    _append_paper_analysis_reference_issues(issues, document_ir, paper_analysis)
    if issues:
        raise ArtifactReferenceError(issues)


def validate_narrative_plan(
    document_ir: DocumentIR,
    paper_analysis: PaperAnalysis,
    evidence_graph: EvidenceGraph,
    narrative_plan: NarrativePlan,
) -> None:
    """Validate NarrativePlan provenance, coverage, and evidence boundaries."""

    issues: list[ReferenceIssue] = []
    for name, paper_id in (
        ("paper_analysis", paper_analysis.paper_id),
        ("evidence_graph", evidence_graph.paper_id),
        ("narrative_plan", narrative_plan.paper_id),
    ):
        if paper_id != document_ir.paper_id:
            issues.append(
                ReferenceIssue(
                    code="PAPER_ID_MISMATCH",
                    path=f"{name}.paper_id",
                    reference=paper_id,
                    message=f"expected {document_ir.paper_id}",
                )
            )
    for actual, expected, path in (
        (
            narrative_plan.analysis_revision,
            paper_analysis.artifact_revision,
            "narrative_plan.analysis_revision",
        ),
        (
            narrative_plan.evidence_revision,
            evidence_graph.artifact_revision,
            "narrative_plan.evidence_revision",
        ),
    ):
        if actual != expected:
            issues.append(
                ReferenceIssue(
                    code="REVISION_MISMATCH",
                    path=path,
                    reference=str(actual),
                    message=f"expected revision {expected}",
                )
            )

    source_ids = {item.source_ref_id for item in document_ir.source_refs}
    claim_ids = {item.claim_id for item in paper_analysis.claims}
    semantic_ids = (
        {item.concept_id for item in paper_analysis.concepts}
        | claim_ids
        | {item.method_id for item in paper_analysis.methods}
        | {item.equation_id for item in paper_analysis.equations}
        | {item.experiment_id for item in paper_analysis.experiments}
        | {
            result.result_id
            for experiment in paper_analysis.experiments
            for result in experiment.results
        }
    )
    evidence_ids = {item.evidence_id for item in evidence_graph.evidence}
    for index, node in enumerate(narrative_plan.nodes):
        base = f"narrative_plan.nodes[{index}]"
        _check_refs(
            issues,
            node.object_refs,
            semantic_ids,
            f"{base}.object_refs",
            "UNKNOWN_SEMANTIC_REF",
        )
        _check_refs(
            issues,
            node.evidence_refs,
            evidence_ids,
            f"{base}.evidence_refs",
            "UNKNOWN_EVIDENCE_REF",
        )
        _check_refs(
            issues,
            node.source_refs,
            source_ids,
            f"{base}.source_refs",
            "UNRESOLVABLE_SOURCE_REF",
        )

    main_claim_ids = {
        item.claim_id for item in paper_analysis.claims if item.claim_type == "main"
    }
    coverage_ids = {item.claim_ref for item in narrative_plan.claim_coverage}
    _check_refs(
        issues,
        coverage_ids,
        claim_ids,
        "narrative_plan.claim_coverage",
        "UNKNOWN_CLAIM_REF",
    )
    for claim_id in sorted(main_claim_ids - coverage_ids):
        issues.append(
            ReferenceIssue(
                code="MAIN_CLAIM_COVERAGE_MISSING",
                path="narrative_plan.claim_coverage",
                reference=claim_id,
                message="every main claim must be included or explicitly omitted",
            )
        )

    nodes_by_id = {item.node_id: item for item in narrative_plan.nodes}
    all_node_refs = {ref for node in narrative_plan.nodes for ref in node.object_refs}
    primary_nodes = [nodes_by_id[node_id] for node_id in narrative_plan.primary_path]
    primary_refs = {ref for node in primary_nodes for ref in node.object_refs}
    for index, coverage in enumerate(narrative_plan.claim_coverage):
        if coverage.disposition == "included" and coverage.claim_ref not in all_node_refs:
            issues.append(
                ReferenceIssue(
                    code="INCLUDED_CLAIM_NOT_NARRATED",
                    path=f"narrative_plan.claim_coverage[{index}]",
                    reference=coverage.claim_ref,
                    message="included claim must appear in a narrative node",
                )
            )
        if coverage.disposition == "omitted" and coverage.claim_ref in primary_refs:
            issues.append(
                ReferenceIssue(
                    code="OMITTED_CLAIM_IN_PRIMARY_PATH",
                    path=f"narrative_plan.claim_coverage[{index}]",
                    reference=coverage.claim_ref,
                    message="omitted claim must not appear in the primary path",
                )
            )

    assessments = {item.claim_id: item for item in evidence_graph.claim_assessments}
    boundary_nodes = [
        node for node in primary_nodes if node.role in {"limitation", "boundary"}
    ]
    for claim_id in sorted(main_claim_ids & primary_refs):
        assessment = assessments.get(claim_id)
        if assessment is not None and assessment.status == "supported":
            continue
        if not any(claim_id in node.object_refs for node in boundary_nodes):
            issues.append(
                ReferenceIssue(
                    code="EVIDENCE_BOUNDARY_MISSING",
                    path="narrative_plan.primary_path",
                    reference=claim_id,
                    message=(
                        "a partially supported or insufficient main claim requires "
                        "a corresponding limitation or boundary node"
                    ),
                )
            )

    if issues:
        raise ArtifactReferenceError(issues)


def validate_artifact_set(
    document_ir: DocumentIR,
    paper_analysis: PaperAnalysis,
    evidence_graph: EvidenceGraph,
    poster_plan: PosterPlan,
    review_result: ReviewResult,
) -> None:
    """Validate revisions, stable IDs, sources, semantic refs, and review targets."""

    issues: list[ReferenceIssue] = []
    artifacts = {
        "document_ir": document_ir,
        "paper_analysis": paper_analysis,
        "evidence_graph": evidence_graph,
        "poster_plan": poster_plan,
        "review_result": review_result,
    }
    for name, artifact in artifacts.items():
        if artifact.paper_id != document_ir.paper_id:
            issues.append(
                ReferenceIssue(
                    code="PAPER_ID_MISMATCH",
                    path=f"{name}.paper_id",
                    reference=artifact.paper_id,
                    message=f"expected {document_ir.paper_id}",
                )
            )

    revision_checks = [
        (
            paper_analysis.source_revision,
            document_ir.artifact_revision,
            "paper_analysis.source_revision",
        ),
        (
            evidence_graph.analysis_revision,
            paper_analysis.artifact_revision,
            "evidence_graph.analysis_revision",
        ),
        (
            poster_plan.analysis_revision,
            paper_analysis.artifact_revision,
            "poster_plan.analysis_revision",
        ),
        (
            poster_plan.evidence_revision,
            evidence_graph.artifact_revision,
            "poster_plan.evidence_revision",
        ),
        (
            review_result.input_revisions.document_ir,
            document_ir.artifact_revision,
            "review_result.input_revisions.document_ir",
        ),
        (
            review_result.input_revisions.paper_analysis,
            paper_analysis.artifact_revision,
            "review_result.input_revisions.paper_analysis",
        ),
        (
            review_result.input_revisions.evidence_graph,
            evidence_graph.artifact_revision,
            "review_result.input_revisions.evidence_graph",
        ),
        (
            review_result.input_revisions.poster_plan,
            poster_plan.artifact_revision,
            "review_result.input_revisions.poster_plan",
        ),
    ]
    for actual, expected, path in revision_checks:
        if actual != expected:
            issues.append(
                ReferenceIssue(
                    code="REVISION_MISMATCH",
                    path=path,
                    reference=str(actual),
                    message=f"expected revision {expected}",
                )
            )

    source_refs = {item.source_ref_id for item in document_ir.source_refs}
    source_equations = {item.source_equation_id for item in document_ir.equations}
    source_assets = {item.asset_id for item in document_ir.assets}

    concept_ids = {item.concept_id for item in paper_analysis.concepts}
    claim_ids = {item.claim_id for item in paper_analysis.claims}
    method_ids = {item.method_id for item in paper_analysis.methods}
    equation_ids = {item.equation_id for item in paper_analysis.equations}
    experiment_ids = {item.experiment_id for item in paper_analysis.experiments}
    result_ids = {
        result.result_id
        for experiment in paper_analysis.experiments
        for result in experiment.results
    }
    semantic_ids = concept_ids | claim_ids | method_ids | equation_ids | experiment_ids | result_ids

    _append_paper_analysis_reference_issues(issues, document_ir, paper_analysis)

    evidence_ids = {item.evidence_id for item in evidence_graph.evidence}
    edge_ids = {item.edge_id for item in evidence_graph.edges}
    evidence_object_ids = semantic_ids | source_assets
    for index, evidence in enumerate(evidence_graph.evidence):
        base = f"evidence_graph.evidence[{index}]"
        _check_refs(issues, evidence.source_refs, source_refs, f"{base}.source_refs", "UNRESOLVABLE_SOURCE_REF")
        _check_refs(issues, evidence.object_refs, evidence_object_ids, f"{base}.object_refs", "UNKNOWN_EVIDENCE_OBJECT")
    for index, edge in enumerate(evidence_graph.edges):
        _check_refs(
            issues,
            [edge.to_claim],
            claim_ids,
            f"evidence_graph.edges[{index}].to_claim",
            "UNKNOWN_CLAIM_REF",
        )
    for index, assessment in enumerate(evidence_graph.claim_assessments):
        _check_refs(
            issues,
            [assessment.claim_id],
            claim_ids,
            f"evidence_graph.claim_assessments[{index}].claim_id",
            "UNKNOWN_CLAIM_REF",
        )
        _check_refs(
            issues,
            assessment.supporting_edges,
            edge_ids,
            f"evidence_graph.claim_assessments[{index}].supporting_edges",
            "UNKNOWN_EDGE_REF",
        )
        for edge_id in assessment.supporting_edges:
            edge = next((item for item in evidence_graph.edges if item.edge_id == edge_id), None)
            if edge is not None and edge.to_claim != assessment.claim_id:
                issues.append(
                    ReferenceIssue(
                        code="EVIDENCE_TARGET_MISMATCH",
                        path=f"evidence_graph.claim_assessments[{index}].supporting_edges",
                        reference=edge_id,
                        message=f"edge targets {edge.to_claim}, not {assessment.claim_id}",
                    )
                )
        for check_index, check in enumerate(assessment.sufficiency_checks):
            _check_refs(
                issues,
                check.source_refs,
                source_refs,
                f"evidence_graph.claim_assessments[{index}].sufficiency_checks[{check_index}].source_refs",
                "UNRESOLVABLE_SOURCE_REF",
            )
    assessed_claims = {item.claim_id for item in evidence_graph.claim_assessments}
    orphan_claims = set(evidence_graph.orphan_claims)
    if assessed_claims & orphan_claims:
        for claim_id in sorted(assessed_claims & orphan_claims):
            issues.append(
                ReferenceIssue(
                    code="CLAIM_GRAPH_STATE_CONFLICT",
                    path="evidence_graph.orphan_claims",
                    reference=claim_id,
                    message="claim cannot be both assessed and orphaned",
                )
            )
    uncovered_claims = claim_ids - assessed_claims - orphan_claims
    for claim_id in sorted(uncovered_claims):
        issues.append(
            ReferenceIssue(
                code="CLAIM_GRAPH_STATE_MISSING",
                path="evidence_graph.claim_assessments",
                reference=claim_id,
                message="claim must be assessed or explicitly orphaned",
            )
        )
    _check_refs(issues, evidence_graph.orphan_claims, claim_ids, "evidence_graph.orphan_claims", "UNKNOWN_CLAIM_REF")
    _check_refs(
        issues,
        evidence_graph.orphan_evidence,
        evidence_ids,
        "evidence_graph.orphan_evidence",
        "UNKNOWN_EVIDENCE_REF",
    )
    linked_evidence = {edge.from_evidence for edge in evidence_graph.edges}
    unclassified_evidence = evidence_ids - linked_evidence - set(evidence_graph.orphan_evidence)
    for evidence_id in sorted(unclassified_evidence):
        issues.append(
            ReferenceIssue(
                code="EVIDENCE_GRAPH_STATE_MISSING",
                path="evidence_graph.edges",
                reference=evidence_id,
                message="evidence must be linked or explicitly orphaned",
            )
        )

    component_ids = {item.component_id for item in poster_plan.components}
    presentation_ids = {
        item.presentation_id for item in poster_plan.source_presentations
    }
    for index, region in enumerate(poster_plan.narrative_regions):
        _check_refs(
            issues,
            region.source_refs,
            source_refs,
            f"poster_plan.narrative_regions[{index}].source_refs",
            "UNRESOLVABLE_SOURCE_REF",
        )
        if region.presentation_ref:
            _check_refs(
                issues,
                [region.presentation_ref],
                presentation_ids,
                f"poster_plan.narrative_regions[{index}].presentation_ref",
                "UNKNOWN_PRESENTATION_REF",
            )
    for index, presentation in enumerate(poster_plan.source_presentations):
        base = f"poster_plan.source_presentations[{index}]"
        _check_refs(issues, [presentation.source_ref_id], source_refs, f"{base}.source_ref_id", "UNRESOLVABLE_SOURCE_REF")
        if presentation.asset_ref:
            _check_refs(issues, [presentation.asset_ref], source_assets, f"{base}.asset_ref", "UNKNOWN_ASSET_REF")
        if presentation.equation_ref:
            _check_refs(issues, [presentation.equation_ref], equation_ids, f"{base}.equation_ref", "UNKNOWN_EQUATION_REF")
        _check_refs(issues, presentation.result_refs, result_ids, f"{base}.result_refs", "UNKNOWN_RESULT_REF")
    for index, component in enumerate(poster_plan.components):
        base = f"poster_plan.components[{index}]"
        _check_refs(issues, component.source_refs, source_refs, f"{base}.source_refs", "UNRESOLVABLE_SOURCE_REF")
        content_targets = semantic_ids | (source_assets if isinstance(component, VisualGalleryComponent) else set())
        _check_refs(issues, component.content_refs, content_targets, f"{base}.content_refs", "UNKNOWN_CONTENT_REF")
        _check_refs(issues, component.claim_refs, claim_ids, f"{base}.claim_refs", "UNKNOWN_CLAIM_REF")
        _check_refs(issues, component.evidence_refs, evidence_ids, f"{base}.evidence_refs", "UNKNOWN_EVIDENCE_REF")
        _check_refs(issues, component.asset_refs, source_assets, f"{base}.asset_refs", "UNKNOWN_ASSET_REF")
        if isinstance(component, MethodFlowComponent):
            _check_refs(issues, component.method_refs, method_ids, f"{base}.method_refs", "UNKNOWN_METHOD_REF")
            for step_index, step in enumerate(component.steps):
                _check_refs(
                    issues,
                    step.source_refs,
                    source_refs,
                    f"{base}.steps[{step_index}].source_refs",
                    "UNRESOLVABLE_SOURCE_REF",
                )
            for panel_index, panel in enumerate(component.inspector_panels):
                panel_base = f"{base}.inspector_panels[{panel_index}]"
                _check_refs(issues, [panel.method_ref], method_ids, f"{panel_base}.method_ref", "UNKNOWN_METHOD_REF")
                _check_refs(issues, panel.equation_refs, equation_ids, f"{panel_base}.equation_refs", "UNKNOWN_EQUATION_REF")
                _check_refs(issues, panel.experiment_refs, experiment_ids, f"{panel_base}.experiment_refs", "UNKNOWN_EXPERIMENT_REF")
                _check_refs(issues, panel.source_refs, source_refs, f"{panel_base}.source_refs", "UNRESOLVABLE_SOURCE_REF")
                _check_refs(issues, panel.presentation_refs, presentation_ids, f"{panel_base}.presentation_refs", "UNKNOWN_PRESENTATION_REF")
        elif isinstance(component, EquationExplorerComponent):
            _check_refs(issues, component.equation_refs, equation_ids, f"{base}.equation_refs", "UNKNOWN_EQUATION_REF")
            for group_index, group in enumerate(component.equation_groups):
                _check_refs(issues, group.equation_refs, equation_ids, f"{base}.equation_groups[{group_index}].equation_refs", "UNKNOWN_EQUATION_REF")
        elif isinstance(component, ClaimEvidenceChainComponent):
            pass
        elif isinstance(component, ResultChartComponent):
            _check_refs(
                issues,
                component.experiment_refs,
                experiment_ids,
                f"{base}.experiment_refs",
                "UNKNOWN_EXPERIMENT_REF",
            )
            _check_refs(issues, component.result_refs, result_ids, f"{base}.result_refs", "UNKNOWN_RESULT_REF")
        elif isinstance(component, VisualGalleryComponent):
            _check_refs(
                issues,
                component.presentation_refs,
                presentation_ids,
                f"{base}.presentation_refs",
                "UNKNOWN_PRESENTATION_REF",
            )

    document_targets = (
        source_refs
        | source_equations
        | source_assets
        | {item.block_id for item in document_ir.blocks}
        | {item.section_id for item in document_ir.sections}
    )
    target_sets = {
        "document_ir": document_targets,
        "paper_analysis": semantic_ids,
        "evidence_graph": evidence_ids | edge_ids | claim_ids,
        "poster_plan": component_ids,
        "html_render": component_ids
        | {"poster:title"}
        | {f"narrative:{role}" for role in ("problem", "motivation", "key_insight")},
        "pdf_render": component_ids
        | {"poster:title"}
        | {f"narrative:{role}" for role in ("problem", "motivation", "key_insight")},
    }
    for index, issue in enumerate(review_result.issues):
        target_id = issue.target.target_id
        if target_id is not None:
            _check_refs(
                issues,
                [target_id],
                target_sets[issue.target.artifact],
                f"review_result.issues[{index}].target.target_id",
                "UNKNOWN_REVIEW_TARGET",
            )
        if issue.suggested_patch is not None:
            patch_target = issue.suggested_patch.target_id
            _check_refs(
                issues,
                [patch_target],
                component_ids,
                f"review_result.issues[{index}].suggested_patch.target_id",
                "UNKNOWN_COMPONENT_REF",
            )
    batch = review_result.repair_batch
    _check_refs(
        issues,
        batch.affected_component_ids,
        component_ids,
        "review_result.repair_batch.affected_component_ids",
        "UNKNOWN_COMPONENT_REF",
    )
    _check_refs(
        issues,
        batch.must_preserve_component_ids,
        component_ids,
        "review_result.repair_batch.must_preserve_component_ids",
        "UNKNOWN_COMPONENT_REF",
    )
    for index, patch in enumerate(batch.operations):
        _check_refs(
            issues,
            [patch.target_id],
            component_ids,
            f"review_result.repair_batch.operations[{index}].target_id",
            "UNKNOWN_COMPONENT_REF",
        )

    if issues:
        raise ArtifactReferenceError(issues)


def load_artifact_set(directory: Path) -> tuple[DocumentIR, PaperAnalysis, EvidenceGraph, PosterPlan, ReviewResult]:
    """Load the canonical five filenames and validate each file structurally."""

    return (
        DocumentIR.model_validate_json((directory / "document_ir.json").read_text(encoding="utf-8")),
        PaperAnalysis.model_validate_json((directory / "paper_analysis.json").read_text(encoding="utf-8")),
        EvidenceGraph.model_validate_json((directory / "evidence_graph.json").read_text(encoding="utf-8")),
        PosterPlan.model_validate_json((directory / "poster_plan.json").read_text(encoding="utf-8")),
        ReviewResult.model_validate_json((directory / "review_result.json").read_text(encoding="utf-8")),
    )
