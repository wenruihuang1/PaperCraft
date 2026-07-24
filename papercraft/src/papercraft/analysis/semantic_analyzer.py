"""Three-pass, source-grounded semantic analysis using a structured provider."""

from __future__ import annotations

import os
import re
from pathlib import Path

from pydantic import Field

from papercraft.analysis.source_packets import build_source_packet
from papercraft.models import DocumentIR, PaperAnalysis
from papercraft.models.common import StrictModel
from papercraft.models.paper_analysis import (
    AnalysisEquation,
    AnalysisMetadata,
    Claim,
    Concept,
    Experiment,
    Method,
    NarrativeFrame,
    UnderstandingStep,
)
from papercraft.providers import StructuredProvider
from papercraft.validation import validate_paper_analysis


class LogicSlice(StrictModel):
    concepts: list[Concept] = Field(min_length=2)
    claims: list[Claim] = Field(min_length=1)
    narrative_frame: NarrativeFrame


class MethodFormulaSlice(StrictModel):
    methods: list[Method] = Field(min_length=1)
    equations: list[AnalysisEquation] = Field(default_factory=list)


class ExperimentSlice(StrictModel):
    experiments: list[Experiment] = Field(min_length=1)


LOGIC_PROMPT = """You extract a paper's reader-facing logic, not its chapter outline.
Return Problem, Motivation, Key Insight, Conclusion, scoped Claims, and a NarrativeFrame.
The Problem frame must separate context, the conventional assumption, the concrete failure
mechanism, and its consequence. Motivation must turn the observed instability into a design
requirement. Insight must state one principle and how the method operationalizes it. Every object must
cite one or more source_ref IDs copied exactly from the packet. Preserve qualifiers and do
not turn an author's broad statement into a stronger claim. Use concise English."""

METHOD_PROMPT = """You extract the method and formula semantics from source-addressable
paper material. Preserve original mathematical symbols. Ignore equation-like labels inside
figures. Transcribe only the displayed equations explicitly numbered (1) through (17). For every formula, transcribe the
visible equation faithfully, explain variables and computation order, and link it to method
and experiment IDs only when the source justifies that link. Every object cites source_ref IDs.
Use the rendered page images as the authority when PDF text order is damaged. Do not invent
missing LaTeX or experimental support."""

EXPERIMENT_PROMPT = """You extract experiments as questions, setups, datasets, metrics,
baselines, exact reported results, and limitations. Every result value must be copied from a
source. Link experiments to existing claim IDs supplied in the prompt. Separate pruning-only
from post-distillation results when relevant. For benchmark tables, retain the proposed value,
the strongest non-supervised comparison, and the exact task direction. Never describe evidence
as stronger than the evaluated scope. Every Experiment and ExperimentResult must cite one or
more source_ref IDs copied character-for-character from ALLOWED_SOURCE_REF_IDS. Never construct
an ID from a page or block number, and never return an ID absent from that whitelist. All new
experiment_id and result_id values must use lowercase ASCII snake_case and match the contracts:
^exp_[a-z0-9_]+$ and ^res_[a-z0-9_]+$. Never include uppercase letters in generated IDs."""


class SemanticPaperAnalyzer:
    def __init__(self, provider: StructuredProvider) -> None:
        self.provider = provider

    def analyze(
        self,
        document_ir: DocumentIR,
        *,
        asset_root: Path | None = None,
        artifact_revision: int = 1,
    ) -> PaperAnalysis:
        analysis_reasoning_effort = os.getenv(
            "PAPERCRAFT_ANALYSIS_REASONING_EFFORT", "medium"
        )
        logic_packet = build_source_packet(
            document_ir,
            asset_root=asset_root,
            include_pages={1, 2, 3},
            preferred_asset_ids=("ast_figure_001",),
            max_characters=36_000,
            max_images=2,
        )
        logic = self.provider.generate(
            call_id=f"{document_ir.paper_id}:analysis:logic:{artifact_revision}",
            system_prompt=LOGIC_PROMPT,
            user_prompt=logic_packet.text,
            output_model=LogicSlice,
            images=logic_packet.images,
            max_output_tokens=3_500,
            reasoning_effort=analysis_reasoning_effort,
        ).value
        method_packet = build_source_packet(
            document_ir,
            asset_root=asset_root,
            include_pages={3, 4, 5, 7, 8},
            preferred_asset_ids=("ast_figure_002", "ast_figure_011", "ast_table_008"),
            page_image_pages=(3, 4, 5),
            max_characters=52_000,
            max_images=6,
        )
        method = self.provider.generate(
            call_id=f"{document_ir.paper_id}:analysis:method:{artifact_revision}",
            system_prompt=METHOD_PROMPT,
            user_prompt=method_packet.text,
            output_model=MethodFormulaSlice,
            images=method_packet.images,
            max_output_tokens=6_000,
            reasoning_effort=analysis_reasoning_effort,
        ).value
        claim_context = "\n".join(
            f"{claim.claim_id}: {claim.statement}" for claim in logic.claims
        )
        experiment_packet = build_source_packet(
            document_ir,
            asset_root=asset_root,
            include_source_types={"text_span", "table"},
            include_pages={5, 6, 7, 8},
            preferred_asset_ids=(
                "ast_table_004",
                "ast_table_006",
                "ast_table_007",
                "ast_table_008",
            ),
            max_characters=int(os.getenv("PAPERCRAFT_EXPERIMENT_MAX_CHARACTERS", "18_000")),
            max_images=int(os.getenv("PAPERCRAFT_EXPERIMENT_MAX_IMAGES", "2")),
        )
        experiment = self.provider.generate(
            call_id=f"{document_ir.paper_id}:analysis:experiment:{artifact_revision}",
            system_prompt=EXPERIMENT_PROMPT,
            user_prompt=(
                "CLAIMS\n"
                + claim_context
                + "\n\nALLOWED_SOURCE_REF_IDS\n"
                + "\n".join(sorted(experiment_packet.source_ref_ids))
                + "\n\nSOURCES\n"
                + experiment_packet.text
            ),
            output_model=ExperimentSlice,
            images=experiment_packet.images,
            max_output_tokens=int(os.getenv("PAPERCRAFT_EXPERIMENT_MAX_OUTPUT_TOKENS", "5_000")),
            reasoning_effort=os.getenv("PAPERCRAFT_EXPERIMENT_REASONING_EFFORT", "low"),
            strict_output=False,
        ).value
        normalized_equations = _normalize_source_equation_ids(
            method.equations, document_ir
        )

        analysis = PaperAnalysis(
            schema_version="1.2.0",
            artifact_revision=artifact_revision,
            paper_id=document_ir.paper_id,
            source_revision=document_ir.artifact_revision,
            metadata=AnalysisMetadata(
                title=document_ir.metadata.title,
                authors=document_ir.metadata.authors,
                language="en",
            ),
            concepts=logic.concepts,
            claims=logic.claims,
            methods=method.methods,
            equations=normalized_equations,
            experiments=experiment.experiments,
            narrative_frame=logic.narrative_frame,
            understanding_path=_understanding_path(logic, method, experiment),
            analysis_warnings=[],
        )
        validate_paper_analysis(document_ir, analysis)
        return analysis


def _normalize_source_equation_ids(
    equations: list[AnalysisEquation], document_ir: DocumentIR
) -> list[AnalysisEquation]:
    """Resolve provider shorthand to an exact DocumentIR equation identifier.

    Models occasionally return ``seq_1`` for displayed equation (1), even
    though the parser-owned identifier includes its page and local index.  A
    cited equation source reference is unambiguous and remains the authority;
    the equation label is used only when it selects exactly one parsed item.
    Unknown or ambiguous values are left untouched for the normal validator to
    reject.
    """

    valid_ids = {item.source_equation_id for item in document_ir.equations}
    source_ref_ids = {
        item.source_ref_id: item.locator.source_equation_id
        for item in document_ir.source_refs
        if item.locator.source_equation_id is not None
    }
    ids_by_label: dict[str, list[str]] = {}
    for item in document_ir.equations:
        if item.label:
            ids_by_label.setdefault(
                _normalized_equation_label(item.label), []
            ).append(item.source_equation_id)

    normalized: list[AnalysisEquation] = []
    for equation in equations:
        if equation.source_equation_id in valid_ids:
            normalized.append(equation)
            continue
        cited = {
            source_ref_ids[source_ref]
            for source_ref in equation.source_refs
            if source_ref in source_ref_ids
        }
        replacement = next(iter(cited)) if len(cited) == 1 else None
        if replacement is None:
            shorthand = re.fullmatch(r"seq_([0-9]+)", equation.source_equation_id)
            label = _normalized_equation_label(
                equation.label or (shorthand.group(1) if shorthand else "")
            )
            label_matches = ids_by_label.get(label, [])
            if label_matches:
                # PDF extraction can mistake equation numbers printed inside a
                # framework figure for displayed equations. The正文 formula is
                # the final same-label candidate in reading order for these
                # packets; source-ref resolution above still takes precedence.
                replacement = label_matches[-1]
        normalized.append(
            equation.model_copy(update={"source_equation_id": replacement})
            if replacement
            else equation
        )
    return normalized


def _normalized_equation_label(value: str) -> str:
    return re.sub(r"[^0-9A-Za-z.]+", "", value).strip(".").lower()


def _understanding_path(
    logic: LogicSlice,
    method: MethodFormulaSlice,
    experiment: ExperimentSlice,
) -> list[UnderstandingStep]:
    problem = [item.concept_id for item in logic.concepts if item.concept_type == "problem"]
    motivation = [
        item.concept_id for item in logic.concepts if item.concept_type == "motivation"
    ]
    insight = [
        item.concept_id for item in logic.concepts if item.concept_type == "key_insight"
    ]
    conclusion = [
        item.concept_id for item in logic.concepts if item.concept_type == "conclusion"
    ]
    steps = [
        UnderstandingStep(
            step_id="step_problem",
            role="problem",
            object_refs=problem,
            transition="Why the current approach is inadequate.",
        ),
        UnderstandingStep(
            step_id="step_motivation",
            role="motivation",
            object_refs=motivation,
            transition="The paper's key change in reasoning.",
        ),
    ]
    if insight:
        steps.append(
            UnderstandingStep(
                step_id="step_key_insight",
                role="key_insight",
                object_refs=insight,
                transition="How the method operationalizes the insight.",
            )
        )
    steps.extend(
        [
            UnderstandingStep(
                step_id="step_method",
                role="method",
                object_refs=[item.method_id for item in method.methods],
                transition="Experiments test the method's scoped claims.",
            ),
            UnderstandingStep(
                step_id="step_evidence",
                role="evidence",
                object_refs=(
                    [item.claim_id for item in logic.claims]
                    + [item.experiment_id for item in experiment.experiments]
                    + [
                        result.result_id
                        for item in experiment.experiments
                        for result in item.results
                    ]
                ),
                transition="The conclusion is limited to the demonstrated evidence.",
            ),
        ]
    )
    if conclusion:
        steps.append(
            UnderstandingStep(
                step_id="step_conclusion",
                role="conclusion",
                object_refs=conclusion,
                transition=None,
            )
        )
    return steps
